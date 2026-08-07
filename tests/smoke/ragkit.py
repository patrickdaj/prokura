"""Shared helpers for the M5 RAG smoke tests.

Mints tokens for an arbitrary realm user (alice, bob) through the same
MCP-Authorization path a real client uses (DCR → OAuth 2.1 + PKCE with the RFC 8707
resource param → aud=mcp-server), then either drives the ``rag_search`` MCP tool or
exchanges (as mcp-server) for a rag-server-audience token to hit ``/rag/search``
directly. The crafted query makes the protected ``secret-roadmap`` the top embedding
hit, so the leakage assertions are meaningful."""

import base64
import hashlib
import html
import json
import re
import secrets

import httpx

from conftest import KEYCLOAK_URL, REALM
from prokura import exchange

MCP_URL = "http://localhost:8140"
RAG_URL = "http://localhost:8150"
REDIRECT = "http://127.0.0.1:9876/callback"

# The adversarial query: 'secret-roadmap' (viewer=alice only) is its top hit.
ADVERSARIAL_QUERY = "When does the Meridian acquisition close? acquisition timeline roadmap"
# A phrase that appears ONLY in the protected doc — its presence in an answer is a leak.
SECRET_MARKER = "Meridian"

_b64 = lambda x: base64.urlsafe_b64encode(x).rstrip(b"=").decode()  # noqa: E731


def token_claims(token: str) -> dict:
    p = token.split(".")[1]
    p += "=" * (-len(p) % 4)
    return json.loads(base64.urlsafe_b64decode(p))


def _register(c: httpx.Client) -> str:
    r = c.post(f"{KEYCLOAK_URL}/realms/{REALM}/clients-registrations/openid-connect",
               headers={"Content-Type": "application/json"},
               json={"client_name": "prokura-rag-smoke", "redirect_uris": [REDIRECT],
                     "token_endpoint_auth_method": "none",
                     "grant_types": ["authorization_code", "refresh_token"],
                     "response_types": ["code"]})
    assert r.status_code == 201, f"DCR failed: {r.status_code} {r.text[:200]}"
    return r.json()["client_id"]


def mcp_token(c: httpx.Client, user: str, password: str) -> str:
    """An aud=mcp-server access token for ``user`` (DCR + OAuth 2.1 + PKCE)."""
    client_id = _register(c)
    verifier = _b64(secrets.token_bytes(32))
    challenge = _b64(hashlib.sha256(verifier.encode()).digest())
    auth = c.get(f"{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/auth", params={
        "client_id": client_id, "response_type": "code", "redirect_uri": REDIRECT,
        "scope": "openid", "state": "s", "code_challenge": challenge,
        "code_challenge_method": "S256", "resource": f"{MCP_URL}/mcp"})
    assert auth.status_code == 200, auth.text[:200]
    cookies = dict(sc.split(";", 1)[0].split("=", 1)
                   for sc in auth.headers.get_list("set-cookie"))
    m = re.search(r'id="kc-form-login"[^>]*action="([^"]+)"', auth.text)
    assert m, "no kc-form-login action on the login page"
    r = c.post(html.unescape(m.group(1)),
               data={"username": user, "password": password},
               headers={"Cookie": "; ".join(f"{k}={v}" for k, v in cookies.items())})
    loc = r.headers.get("location", "")
    assert loc.startswith(REDIRECT), f"login did not redirect: {r.status_code} {loc[:120]}"
    code = httpx.URL(loc).params.get("code")
    tok = c.post(f"{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/token", data={
        "grant_type": "authorization_code", "client_id": client_id, "code": code,
        "redirect_uri": REDIRECT, "code_verifier": verifier, "resource": f"{MCP_URL}/mcp"})
    assert tok.status_code == 200, tok.text[:200]
    return tok.json()["access_token"]


def rag_token(mcp_tok: str) -> str:
    """Exchange an mcp-server-audience token for a rag-server-audience one, as the
    mcp-server client (the same exchange rag_search performs). sub is preserved."""
    return exchange(mcp_tok, "rag-server", scopes=["rag-audience"],
                    base_url=KEYCLOAK_URL, realm=REALM,
                    client_id="mcp-server", client_secret="mcp-server-dev-secret")


def search_direct(rag_tok: str, query: str = ADVERSARIAL_QUERY, **body) -> httpx.Response:
    """Call POST /rag/search directly with a (possibly foreign) bearer token."""
    payload = {"query": query, **body}
    return httpx.post(f"{RAG_URL}/rag/search",
                      headers={"Authorization": f"Bearer {rag_tok}"},
                      json=payload, timeout=20.0)


def search_via_mcp(c: httpx.Client, mcp_tok: str, query: str = ADVERSARIAL_QUERY) -> tuple[dict, bool]:
    """Call the rag_search MCP tool; return (structured result, isError)."""
    r = c.post(f"{MCP_URL}/mcp", headers={"Authorization": f"Bearer {mcp_tok}"},
               json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                     "params": {"name": "rag_search", "arguments": {"query": query}}})
    r.raise_for_status()
    result = r.json()["result"]
    payload = json.loads(result["content"][0]["text"])
    return payload, result.get("isError", False)


def doc_ids(result: dict) -> set[str]:
    return {c["doc_id"] for c in result.get("chunks", [])}
