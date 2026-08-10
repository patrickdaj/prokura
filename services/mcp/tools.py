"""The MCP tools that drive the delegation chain.

Both tools obtain a correctly-audienced token by RFC 8693 exchange (see
exchange.py) — the inbound MCP token is NEVER forwarded downstream. The tools
are the M4 headline: a real MCP client, holding only an ``aud=mcp-server`` token,
reaches the broker (consent-gated) and the gated email action (human-approved)
without ever handling a broker- or tools-audience token itself.
"""

import httpx

import audit
import config
from exchange import ExchangeError, exchange_for
from prokura_telemetry import stamp_flow, tracer


class ToolError(Exception):
    """A tool failed for a protocol or transport reason (surfaced as isError)."""


# Declared tool surface returned by tools/list.
TOOL_SPECS = [
    {
        "name": "get_provider_token",
        "description": "Obtain a short-lived third-party provider access token via "
                       "the Prokura Token Broker. Subject to per-agent consent.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "provider": {"type": "string", "description": "Provider alias, e.g. 'acme'."},
                "scopes": {"type": "array", "items": {"type": "string"},
                           "description": "Requested scopes (must be within the grant)."},
            },
            "required": ["provider"],
        },
    },
    {
        "name": "send_email",
        "description": "Send an email. A sensitive action: the first call is refused "
                       "with an approval_required challenge (ref + action_token) and "
                       "the human is notified out-of-band. Wait for them to decide, "
                       "then call again with the action_token to execute. There is "
                       "nothing else for you to do — the approval happens entirely "
                       "outside your reach.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "to": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
                "action_token": {"type": "string",
                                 "description": "Returned by the approval challenge; "
                                                "present it after approval to execute."},
            },
            "required": ["to", "subject", "body"],
        },
    },
    {
        "name": "rag_search",
        "description": "Search the document corpus and return only the passages the "
                       "querying user is authorized to see. Retrieval is filtered by "
                       "OpenFGA as the END USER (not the agent): an unauthorized "
                       "document is never returned, even if it is the top match.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural-language query."},
                "top_k": {"type": "integer",
                          "description": "Max candidate documents to authorize (optional)."},
            },
            "required": ["query"],
        },
    },
]


def get_provider_token(inbound_token: str, claims: dict, args: dict) -> dict:
    """Exchange the inbound token for a broker-audience token and hand it to the
    broker, which enforces grant + scope + per-agent consent (agent=mcp-server)."""
    provider = args.get("provider")
    if not provider:
        raise ToolError("provider is required")
    scopes = args.get("scopes", []) or []
    user = claims.get("preferred_username")
    with tracer().start_as_current_span("tool.get_provider_token") as span:
        span.set_attribute("prokura.provider", provider)
        stamp_flow("B", user=user, agent=config.MCP_CLIENT_ID, provider=provider)
        try:
            broker_token = exchange_for(inbound_token, config.BROKER_AUDIENCE)
        except ExchangeError as e:
            audit.emit(decision="exchange_failed", user=user, agent=config.MCP_CLIENT_ID,
                       tool="get_provider_token", detail=str(e))
            raise ToolError("token_exchange_failed") from e
        r = httpx.post(f"{config.BROKER_URL}/v1/tokens/{provider}",
                       headers={"Authorization": f"Bearer {broker_token}"},
                       json={"scopes": scopes}, timeout=20.0)
    if r.status_code != 200:
        detail = _err(r)
        audit.emit(decision="broker_denied", user=user, agent=config.MCP_CLIENT_ID,
                   tool="get_provider_token", detail=detail)
        raise ToolError(f"broker refused ({r.status_code}): {detail}")
    audit.emit(decision="provider_token_issued", user=user, agent=config.MCP_CLIENT_ID,
               tool="get_provider_token", detail=provider)
    return r.json()


def send_email(inbound_token: str, claims: dict, args: dict) -> dict:
    """Drive the reactive-approval action. Without an action_token the tools-API
    refuses with a challenge (which we relay); with one it executes exactly once.
    The tools-API sees only the exchanged tools-audience token, never the inbound."""
    params = {k: args.get(k) for k in ("to", "subject", "body")}
    if not all(params.values()):
        raise ToolError("to, subject, body are required")
    action_token = args.get("action_token")
    user = claims.get("preferred_username")

    with tracer().start_as_current_span("tool.send_email") as span:
        span.set_attribute("prokura.action", "email.send")
        stamp_flow("C", user=user, agent=config.MCP_CLIENT_ID)
        try:
            tools_token = exchange_for(inbound_token, config.TOOLS_AUDIENCE)
        except ExchangeError as e:
            audit.emit(decision="exchange_failed", user=user, agent=config.MCP_CLIENT_ID,
                       tool="send_email", detail=str(e))
            raise ToolError("token_exchange_failed") from e
        body = dict(params)
        if action_token:
            body["action_token"] = action_token
        r = httpx.post(f"{config.TOOLS_URL}/tools/email/send",
                       headers={"Authorization": f"Bearer {tools_token}"},
                       json=body, timeout=20.0)

    # Reactive approval challenge (the tools-API registered the real action and
    # the approval service already initiated the ceremony — ADR-0022). The
    # agent's ONLY move is to wait for the human and retry with the token.
    if r.status_code == 428:
        j = r.json()
        audit.emit(decision="approval_required", user=user, agent=config.MCP_CLIENT_ID,
                   tool="send_email", detail=j.get("ref"))
        return {"status": "approval_required", "ref": j.get("ref"),
                "action_token": j.get("action_token"),
                "message": "Approval required. The user has been notified and will "
                           "approve or deny in their own session. Wait, then call "
                           "send_email again with this action_token. Do not attempt "
                           "to obtain the approval yourself."}
    if r.status_code != 200:
        detail = _err(r)
        audit.emit(decision="send_refused", user=user, agent=config.MCP_CLIENT_ID,
                   tool="send_email", detail=detail)
        raise ToolError(f"send refused ({r.status_code}): {detail}")
    audit.emit(decision="email_sent", user=user, agent=config.MCP_CLIENT_ID,
               tool="send_email", detail=params["to"])
    return {"status": "sent", **r.json()}


def rag_search(inbound_token: str, claims: dict, args: dict) -> dict:
    """Exchange the inbound token for a rag-server-audience token and hand it to the
    RAG retriever, which authorizes candidate chunks as the end user (never the
    agent). The inbound MCP token is never forwarded — only the exchanged
    rag-audience token reaches the retriever, and the ``sub`` it carries is the end
    user, so the retriever's FGA check runs as that user."""
    query = args.get("query")
    if not query:
        raise ToolError("query is required")
    user = claims.get("preferred_username")
    body = {"query": query}
    if args.get("top_k"):
        body["top_k"] = args["top_k"]
    with tracer().start_as_current_span("tool.rag_search") as span:
        span.set_attribute("prokura.rag.query_len", len(query))
        stamp_flow("D", user=user, agent=config.MCP_CLIENT_ID)
        try:
            rag_token = exchange_for(inbound_token, config.RAG_AUDIENCE)
        except ExchangeError as e:
            audit.emit(decision="exchange_failed", user=user, agent=config.MCP_CLIENT_ID,
                       tool="rag_search", detail=str(e))
            raise ToolError("token_exchange_failed") from e
        r = httpx.post(f"{config.RAG_URL}/rag/search",
                       headers={"Authorization": f"Bearer {rag_token}"},
                       json=body, timeout=20.0)
    if r.status_code != 200:
        detail = _err(r)
        audit.emit(decision="rag_denied", user=user, agent=config.MCP_CLIENT_ID,
                   tool="rag_search", detail=detail)
        raise ToolError(f"retriever refused ({r.status_code}): {detail}")
    result = r.json()
    audit.emit(decision="rag_retrieved", user=user, agent=config.MCP_CLIENT_ID,
               tool="rag_search", detail=f"allowed={result.get('allowed')}")
    return result


def dispatch(name: str, inbound_token: str, claims: dict, args: dict) -> dict:
    if name == "get_provider_token":
        return get_provider_token(inbound_token, claims, args)
    if name == "send_email":
        return send_email(inbound_token, claims, args)
    if name == "rag_search":
        return rag_search(inbound_token, claims, args)
    raise ToolError(f"unknown tool: {name!r}")


def _err(r: httpx.Response) -> str:
    """SR-01: relay only the downstream service's stable machine code (every
    prokura service now emits {error: <code>}); free text never propagates."""
    if r.headers.get("content-type", "").startswith("application/json"):
        code = r.json().get("error", "")
        if isinstance(code, str) and code and len(code) <= 64:
            return code
    return "upstream_error"
