# Prokura MCP server (M4)

Makes the M0–M3 delegation chain reachable by any standard **MCP client** through
MCP's authorization model (MCP Authorization **2025-06-18**), with **Keycloak as
the MCP authorization server**.

## Two hats

- **OAuth 2.1 resource server**
  - Serves **RFC 9728** Protected Resource Metadata at
    `/.well-known/oauth-protected-resource`, naming the Keycloak realm as the
    authorization server.
  - An unauthenticated protected request (`POST /mcp`) gets `401` +
    `WWW-Authenticate: Bearer resource_metadata="…"`, so a client can discover
    where to authenticate.
  - Validates the inbound access token's audience (`aud=mcp-server`, the M1
    defense). The audience is bound by the `mcp-audience` **client scope**, not the
    RFC 8707 `resource` parameter — Keycloak does not reflect `resource` into `aud`
    (the documented gap).

- **Minimal MCP server** over streamable-HTTP JSON-RPC at `POST /mcp`:
  `initialize`, `tools/list`, `tools/call`. Two tools drive the chain:
  - `get_provider_token(provider, scopes?)` → Token Broker (consent-gated).
  - `send_email(to, subject, body, action_token?)` → Tools-API, **reactive
    approval**: the first call is refused with an `approval_required` challenge
    carrying a `ref` + `action_token`; the client completes CIBA for that `ref`
    (binding_message=ref) and calls again with the `action_token` to execute.

## Never forwards the inbound token

Every downstream call first **exchanges** the inbound MCP token (RFC 8693, as the
confidential `mcp-server` client) for a token addressed to the right audience
(`token-broker` / `agent-tools-api`). The exchanged token carries
`azp=mcp-server`, so **`mcp-server` is the consent "agent" identity** — the
documented agent-identity choice (design §3): Keycloak sets `azp` to the
requesting client on exchange, so preserving the (public, freshly-DCR'd) MCP
client id isn't clean, and `mcp-server` is the honest agent acting for the user.

## Security note — DCR "any client can register"

With Dynamic Client Registration enabled (so a real MCP client can self-register),
*any* client can obtain a client id. Registration grants nothing by itself:
**per-agent consent** (M2) gates a registered client's access to a user's grants,
and **human approval** (M3) gates sensitive actions. See `docs/threat-model.md`.

Port **8140**. Fire-and-forget telemetry (no `depends_on: lgtm`).
