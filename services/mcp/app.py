"""Prokura MCP server (M4) — an OAuth 2.1 resource server that is also a minimal
MCP server, per MCP Authorization (2025-06-18).

Two hats:
  * Resource server — serves RFC 9728 Protected Resource Metadata at
    /.well-known/oauth-protected-resource, challenges unauthenticated protected
    requests with 401 + WWW-Authenticate: Bearer resource_metadata="…", and
    validates the inbound access token's audience (aud=mcp-server, the M1 defense).
  * MCP server — a minimal streamable-HTTP JSON-RPC surface (initialize,
    tools/list, tools/call) exposing tools that drive the delegation chain.

The inbound MCP token is never forwarded downstream; each tool exchanges it
(RFC 8693) for a correctly-audienced token first (see tools.py / exchange.py).

Born instrumented: traceparent join key + prokura.correlation_id, realtime audit.
"""

from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse

import config
import tools
import validation
from telemetry import setup_telemetry

app = FastAPI(title="prokura-mcp")
setup_telemetry(app)

_METADATA_URL = f"{config.MCP_PUBLIC_URL}/.well-known/oauth-protected-resource"
_WWW_AUTH = f'Bearer resource_metadata="{_METADATA_URL}"'


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


@app.get("/.well-known/oauth-protected-resource")
def protected_resource_metadata() -> JSONResponse:
    """RFC 9728: names the Keycloak realm as this resource's authorization
    server, so a client that hit the 401 can discover where to authenticate."""
    return JSONResponse({
        "resource": config.MCP_RESOURCE,
        "authorization_servers": [config.KEYCLOAK_ISSUER],
        "bearer_methods_supported": ["header"],
        # Clients echo these into DCR and the authorization request, so only
        # advertise scopes the realm's anonymous DCR policy admits (realm
        # defaults) — advertising openid here used to break registration.
        # offline_access rides along because Keycloak's DCR-with-scope assignment
        # REPLACES realm defaults: a client that registers without it loses it,
        # then fails invalid_scope when requesting a refresh-capable session.
        "scopes_supported": [config.MCP_SCOPE, "offline_access"],
    })


def _challenge() -> JSONResponse:
    return JSONResponse({"error": "unauthorized"}, status_code=401,
                        headers={"WWW-Authenticate": _WWW_AUTH})


def _insufficient_scope() -> JSONResponse:
    # RFC 6750 §3.1: right resource, but the grant does not cover it — 403, and
    # the challenge names the scope the client should request.
    www = (f'Bearer error="insufficient_scope", scope="{config.MCP_SCOPE}", '
           f'resource_metadata="{_METADATA_URL}"')
    return JSONResponse({"error": "insufficient_scope"}, status_code=403,
                        headers={"WWW-Authenticate": www})


@app.post("/mcp")
async def mcp_endpoint(request: Request,
                       authorization: str | None = Header(default=None)) -> JSONResponse:
    # Transport-level auth (MCP 2025-06-18): an unauthenticated or wrong-audience
    # request gets a 401 pointing at the resource metadata — never a tool action.
    if not authorization or not authorization.lower().startswith("bearer "):
        return _challenge()
    token = authorization.split(" ", 1)[1]
    try:
        claims = validation.verify_bearer(token)
    except (validation.TokenInvalid, validation.WrongAudience):
        return _challenge()
    except validation.InsufficientScope:
        return _insufficient_scope()

    try:
        msg = await request.json()
    except Exception:
        return _rpc_error(None, -32700, "parse error")

    method = msg.get("method")
    msg_id = msg.get("id")

    # Notifications (no id) — acknowledge with 202, no body.
    if msg_id is None:
        return JSONResponse(status_code=202, content=None)

    if method == "initialize":
        return _rpc_ok(msg_id, {
            "protocolVersion": config.MCP_PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "prokura-mcp", "version": "0.1.0"},
        })
    if method == "tools/list":
        return _rpc_ok(msg_id, {"tools": tools.TOOL_SPECS})
    if method == "tools/call":
        params = msg.get("params", {})
        name = params.get("name", "")
        args = params.get("arguments", {}) or {}
        try:
            result = tools.dispatch(name, token, claims, args)
        except tools.ToolError as e:
            return _tool_result(msg_id, str(e), is_error=True)
        return _tool_result(msg_id, result)
    return _rpc_error(msg_id, -32601, f"method not found: {method}")


def _rpc_ok(msg_id, result) -> JSONResponse:
    return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "result": result})


def _rpc_error(msg_id, code: int, message: str) -> JSONResponse:
    return JSONResponse({"jsonrpc": "2.0", "id": msg_id,
                         "error": {"code": code, "message": message}})


def _tool_result(msg_id, payload, is_error: bool = False) -> JSONResponse:
    """MCP tools/call result: content blocks + isError. We serialize the tool's
    structured output as JSON text (the MCP content convention)."""
    import json
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return _rpc_ok(msg_id, {"content": [{"type": "text", "text": text}], "isError": is_error})
