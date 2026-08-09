"""Scripted, spec-compliant MCP client for the M4 smoke tests.

Performs the exact MCP Authorization (2025-06-18) handshake — discover (401 →
PRM → AS metadata), dynamic client registration (RFC 7591), OAuth 2.1 + PKCE with
the RFC 8707 resource param — and speaks the minimal MCP JSON-RPC surface
(initialize / tools/list / tools/call) over streamable HTTP. A real MCP client
(Claude among them) uses the same standard steps."""

import base64
import hashlib
import json
import re
import secrets

import httpx

from conftest import KEYCLOAK_URL, REALM

MCP_URL = "http://localhost:8140"
MCP_ENDPOINT = f"{MCP_URL}/mcp"
METADATA_URL = f"{MCP_URL}/.well-known/oauth-protected-resource"
REDIRECT = "http://127.0.0.1:9876/callback"

_b64 = lambda x: base64.urlsafe_b64encode(x).rstrip(b"=").decode()  # noqa: E731


def claims(token: str) -> dict:
    p = token.split(".")[1]
    p += "=" * (-len(p) % 4)
    return json.loads(base64.urlsafe_b64decode(p))


# --- Discovery (RFC 9728 → RFC 8414) ------------------------------------------

def discover_challenge(c: httpx.Client) -> str:
    """An unauthenticated protected request returns 401 + WWW-Authenticate whose
    resource_metadata points at the PRM. Returns that metadata URL."""
    r = c.post(MCP_ENDPOINT, json={"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert r.status_code == 401, f"expected 401 challenge, got {r.status_code}"
    www = r.headers.get("WWW-Authenticate", "")
    m = re.search(r'resource_metadata="([^"]+)"', www)
    assert m, f"no resource_metadata in WWW-Authenticate: {www!r}"
    return m.group(1)


def as_metadata(c: httpx.Client) -> dict:
    r = c.get(f"{KEYCLOAK_URL}/realms/{REALM}/.well-known/oauth-authorization-server")
    r.raise_for_status()
    return r.json()


# --- DCR (RFC 7591) + OAuth 2.1 + PKCE ----------------------------------------

def register_client(c: httpx.Client, reg_endpoint: str | None = None,
                    scope: str | None = None) -> str:
    """Register a public client (RFC 7591). Pass scope to mirror real MCP clients
    (Claude among them), which echo the PRM's scopes_supported into the DCR body."""
    reg_endpoint = reg_endpoint or f"{KEYCLOAK_URL}/realms/{REALM}/clients-registrations/openid-connect"
    body = {"client_name": "prokura-mcp-smoke", "redirect_uris": [REDIRECT],
            "token_endpoint_auth_method": "none",
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"]}
    if scope:
        body["scope"] = scope
    reg = c.post(reg_endpoint, headers={"Content-Type": "application/json"}, json=body)
    assert reg.status_code == 201, f"DCR failed: {reg.status_code} {reg.text[:300]}"
    return reg.json()["client_id"]


def login(c: httpx.Client, client_id: str, scope: str = "openid",
          user: str = "alice") -> str:
    """OAuth 2.1 authorization code + PKCE, sending the RFC 8707 resource param.
    The HUMAN leg — the real login page, plus the consent screen every DCR
    client requires — is played by humankit in a browser (M7 quarantine: this
    kit holds no user credential). Returns the access token (aud=mcp-server)."""
    import humankit

    verifier = _b64(secrets.token_bytes(32))
    challenge = _b64(hashlib.sha256(verifier.encode()).digest())
    auth_url = str(httpx.URL(
        f"{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/auth",
        params={"client_id": client_id, "response_type": "code",
                "redirect_uri": REDIRECT, "scope": scope, "state": "s",
                "code_challenge": challenge, "code_challenge_method": "S256",
                "resource": f"{MCP_URL}/mcp"}))
    final = humankit.auth_code_login(auth_url, REDIRECT, user=user)
    code = httpx.URL(final).params.get("code")
    assert code, f"no code on redirect: {final[:150]}"
    tok = c.post(f"{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/token", data={
        "grant_type": "authorization_code", "client_id": client_id, "code": code,
        "redirect_uri": REDIRECT, "code_verifier": verifier, "resource": f"{MCP_URL}/mcp"})
    assert tok.status_code == 200, tok.text[:300]
    return tok.json()["access_token"]


def mcp_token(c: httpx.Client) -> str:
    """End-to-end: DCR a client, then OAuth 2.1 + PKCE → an aud=mcp-server token."""
    return login(c, register_client(c))


# --- MCP JSON-RPC over streamable HTTP ----------------------------------------

def rpc(c: httpx.Client, token: str, method: str, params: dict | None = None,
        msg_id=1) -> httpx.Response:
    return c.post(MCP_ENDPOINT, headers={"Authorization": f"Bearer {token}"},
                  json={"jsonrpc": "2.0", "id": msg_id, "method": method,
                        "params": params or {}})


def tool_call(c: httpx.Client, token: str, name: str, arguments: dict) -> tuple[dict, bool]:
    """Call a tool; return (parsed structured output, isError)."""
    r = rpc(c, token, "tools/call", {"name": name, "arguments": arguments})
    r.raise_for_status()
    result = r.json()["result"]
    text = result["content"][0]["text"]
    try:
        payload = json.loads(text)
    except ValueError:
        payload = {"text": text}
    return payload, result.get("isError", False)
