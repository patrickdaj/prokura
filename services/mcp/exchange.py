"""RFC 8693 token exchange, from inside the MCP server's trust boundary.

The MCP server never forwards the inbound MCP token downstream. Instead it
exchanges that token — as the confidential ``mcp-server`` client — into a fresh
token addressed to a specific downstream audience (``token-broker`` or
``agent-tools-api``). The inbound token names ``mcp-server`` in its ``aud`` (the
mcp-audience client scope), which is what permits ``mcp-server`` to exchange it.

The exchanged token carries ``azp=mcp-server`` and the acting user's identity
(``sub``/``preferred_username`` from the subject), so downstream the *agent* is
``mcp-server`` — the consent identity — acting for the user. This is the
documented agent-identity choice (design §3): Keycloak's exchange sets ``azp`` to
the requesting client, so ``mcp-server`` is the honest agent, not the (public,
freshly-DCR'd) MCP client. Tokens are transient and never logged."""

import httpx

import config
from prokura_telemetry import tracer

_GRANT = "urn:ietf:params:oauth:grant-type:token-exchange"
_ACCESS = "urn:ietf:params:oauth:token-type:access_token"

# downstream audience -> the realm client scope whose audience mapper adds it
_AUDIENCE_SCOPE = {
    config.BROKER_AUDIENCE: "broker-audience",
    config.TOOLS_AUDIENCE: "tools-audience",
    config.RAG_AUDIENCE: "rag-audience",
}


class ExchangeError(Exception):
    pass


def exchange_for(subject_token: str, audience: str) -> str:
    """Exchange the inbound MCP token for one addressed to ``audience``.
    Returns the raw access token string."""
    data = {
        "grant_type": _GRANT,
        "client_id": config.MCP_CLIENT_ID,
        "client_secret": config.MCP_CLIENT_SECRET,
        "subject_token": subject_token,
        "subject_token_type": _ACCESS,
        "audience": audience,
    }
    scope = _AUDIENCE_SCOPE.get(audience)
    if scope:
        data["scope"] = scope
    with tracer().start_as_current_span("keycloak.mcp_exchange") as span:
        span.set_attribute("prokura.exchange.audience", audience)
        r = httpx.post(
            f"{config.KEYCLOAK_INTERNAL}/realms/{config.REALM}/protocol/openid-connect/token",
            data=data, timeout=15.0,
        )
    if r.status_code != 200:
        raise ExchangeError(f"exchange for aud={audience} failed: {r.status_code} {r.text[:200]}")
    return r.json()["access_token"]
