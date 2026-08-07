# Threat model (working draft)

> Started in M2 to satisfy the `token-brokering` spec's TTL-honesty and
> trusted-tuple-writer requirements. The full threat model — assets, actors,
> STRIDE per flow, and mitigations — is an M6 deliverable; this file currently
> covers only what M2 makes concrete. Non-production (docker-compose) throughout.

## Trusted Computing Base (TCB)

Everything behind the compose network that can mint, broker, or gate credentials
is trusted:

- **Keycloak** — issues user/agent tokens, brokers third-party grants (Store
  Tokens), and is the sole identity authority.
- **Token Broker** — holds every third-party refresh credential (in OpenBao),
  performs provider refresh, and is the **sole writer of OpenFGA `can_use`
  tuples**. It enforces `operator == grant owner` at tuple-write time (the
  invariant is in broker code, not the FGA model — F1-A/Q3-B), and refuses +
  logs any cross-user write. A compromise of the broker compromises all grants;
  it is deliberately minimal and least-privileged (its OpenBao token is scoped to
  `secret/data/grants/*` only).
- **OpenBao** — the only store of long-lived provider credentials. Credentials
  are held in broker memory transiently during a refresh and never appear in any
  API response, log line, or audit record (asserted by
  `test_no_provider_token_in_logs`).
- **OpenFGA** — the per-agent consent authority (`can_use`). With Dynamic Client
  Registration enabled for MCP (M4), any client can register itself; the
  `can_use` tuple is the gate between a registered client and a user's grants.

- **Approval service** (M3) — the CIBA-gated human-approval authority. It holds
  the structured action payload and its hash, renders the human-facing approval
  surface itself (never agent-authored text), relays the human's decision to
  Keycloak's CIBA callback, and is the sole issuer + introspector of the
  single-use action token. It joins the TCB: a compromise could approve actions,
  so decisions are only accepted from an authenticated session and every
  register/delegate/decision/consume event is audited.
- **Tools-API** (M3) — the resource server for the gated `email.send` action. It
  is not fully trusted to *decide*, but it enforces the gate: audience check
  (M1 defense) plus hash-verify + single-use consume against the approval service
  before any action runs.

Agents and MCP clients are **outside** the TCB: an agent can obtain a provider
token only by presenting a broker-audience token (RFC 8693, `aud=token-broker`)
for a grant its user owns AND for which the user has consented to that specific
agent. The read-token capability that retrieves a Keycloak-stored credential
stays inside the broker (the broker re-exchanges the incoming token as its own
confidential client), so an agent can never retrieve a stored credential directly
from Keycloak's `/broker/{alias}/token` endpoint.

## TTL honesty table

The broker caps every hand-out at **900 s** (`expires_in ≤ 900`), regardless of
the underlying provider token's real lifetime. Residual validity *beyond* the
hand-out interval is provider-controlled and is stated here honestly — the broker
never claims a provider token expires at 15 minutes.

| Provider | Wired in v0 | Hand-out cap | Provider-side residual validity | Refresh |
|----------|-------------|--------------|---------------------------------|---------|
| `acme` (mock realm) | yes | 900 s | access token 3600 s; refresh credential lives with the acme SSO session (set to 30 days in the mock realm so the demo grant stays usable — a real provider's refresh token is not Keycloak-session-bound) | yes (`supports_refresh: true`) |
| GitHub (GitHub App) | BYO extension | 900 s | user access token ~8 h | yes |
| Google | BYO extension | 900 s | access token ~1 h | yes |

**Scope narrowing:** `acme` declares `supports_scope_narrowing: false`. A
narrowing request within granted scopes returns the token with its *actual*
scopes and reports them honestly — the broker never fakes narrowing and never
silently widens.

## Human approval (Flow C, M3)

- **Trusted rendering.** The approval UI renders the action, params, agent, and
  scopes from the approval service's stored payload — never from any
  agent-supplied string. The CIBA `binding_message` carries only a reference ID
  (Keycloak-validated `^[a-zA-Z0-9-._+/!?#]{1,50}$`), so agent-authored prose
  never reaches the human.
- **Single-use, hash-bound action token.** The approval service issues the action
  token and is its sole introspector. Before `email.send` runs, the tools-API
  verifies the action+params hash equals the approved hash (parameter tampering
  is refused) and the approval service **atomically consumes** the reference
  (replay is refused). Both are asserted by tests.
- **Inert notifications.** ntfy is deny-all; only the approval service may publish
  (Basic auth), to per-user unguessable topics. A notification carries only a
  reference ID + deep link — no action params — and a fabricated publish is
  refused (403) and changes no approval state. Decisions happen only in the
  authenticated UI.
- **Clean abort.** On denial or the 30 s CIBA timeout, the agent's poll returns an
  error, no action token is usable, and the action never runs.
- **Trigger on the resource server (done, M4).** The approval *trigger* now lives
  on the resource server (reactive step-up, RFC 9470-style), not on the agent. A
  sensitive call arriving without an action token is refused with a `428`
  `approval_required` challenge, and the tools-API itself registers the exact
  `{action, params}` it observed with the approval service (recording the hash);
  the agent then runs the (client-initiated) CIBA flow for that reference id and
  retries. The un-bypassable trigger is on the server, and **the action that gets
  approved is the one the server saw, not one the agent described**. Enforcement,
  hash-binding, and single-use are unchanged from M3 (asserted by
  `test_reactive_approval`) — only who initiates the ceremony moved.

## MCP authorization (Flow D, M4)

M4 makes the delegation chain reachable by any standard **MCP client** through
MCP's authorization model (MCP Authorization **2025-06-18**), with **Keycloak as
the MCP authorization server** and the Prokura **MCP server** (`services/mcp/`,
port 8140) as an OAuth 2.1 **resource server**. The MCP server joins the TCB as
an orchestrator: it validates inbound tokens, exchanges for downstream ones, and
drives the broker and the gated tool on the user's behalf.

- **DCR: "any client can register → consent is the gate."** So a real MCP client
  can self-register, the realm permits **anonymous Dynamic Client Registration**
  (RFC 7591) for clients whose redirect URIs are localhost (the Trusted Hosts
  policy: `host-sending-registration-request-must-match=false`,
  `client-uris-must-match=true`). The consequence is stated plainly: **any client
  can register**. Registration grants *nothing* by itself — a freshly-registered
  client gets an `aud=mcp-server` token and no more. Access to a user's provider
  grants still requires **per-agent consent** (M2, the `can_use` tuple), and every
  sensitive action still requires **human approval** (M3). Consent and approval —
  not registration — are the gates.

- **Audience binding without RFC 8707 (documented gap + workaround).** MCP expects
  the OAuth `resource` parameter (RFC 8707) to bind a token to a specific server.
  Keycloak does **not** reflect `resource` into the token `aud` (confirmed in the
  M4 spike: `aud` came back `null`). The workaround, matching the M1/M2 audience
  pattern, is the **`mcp-audience` client scope** (an `oidc-audience-mapper` →
  `mcp-server`) made a **realm-default** scope, so every DCR-registered client
  carries `aud=mcp-server`. The MCP server validates it (the M1 audience defense);
  the client still sends `resource` per spec, but binding does not depend on it.

- **No token passthrough.** The MCP server **never forwards the inbound MCP token**
  downstream. For each downstream call it performs an **RFC 8693 exchange** (as the
  confidential `mcp-server` client) into a token addressed to the specific
  audience (`token-broker` / `agent-tools-api`). The inbound token names
  `mcp-server` in its `aud`, which is what permits the exchange. Presenting the raw
  MCP token to the broker is refused (wrong audience) — asserted by
  `test_inbound_mcp_token_never_forwarded_downstream`. A token minted for the wrong
  resource is refused at the MCP boundary too (`401` + `WWW-Authenticate` pointing
  at the RFC 9728 metadata).

- **Agent identity for consent.** The exchanged token carries `azp=mcp-server`
  (Keycloak sets `azp` to the requesting client on exchange), so the consent
  "agent" is **`mcp-server`** — one consent for "the MCP server acting for you."
  This is the documented trade-off (design §3): it does not preserve the
  individual DCR client id as a distinct consent principal, so per-MCP-client
  consent is coarser than the "each registered client is gated separately" ideal.
  It is honest and enforceable (the MCP server is in the TCB and is the sole
  exchange subject); finer-grained per-DCR-client consent is a future refinement.

## Known residual risks (M2 scope)

- **Broker is a high-value single point of trust** (sole tuple writer + holds all
  refresh credentials). Mitigations above; hardening (rotation policy, mTLS
  between services, HA) is out of scope for the non-production reference.
- **Mock provider session lifespan** is stretched to 30 days for demo
  convenience; a production integration would use the real provider's refresh
  token, which the broker persists (including rotation) on each refresh.
