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
- **Known refinement — move the trigger to the resource server.** In the current
  cut the *agent* initiates the approval ceremony and the tools-API only verifies
  at execution. Enforcement is already server-side (the tool refuses without an
  approved, hash-bound, single-use token), but the *trigger* depends on the agent
  choosing to ask, which is influenceable. The intended design is reactive
  step-up (RFC 9470-style): the agent attempts the action, the tools-API refuses
  with an `approval_required` challenge and registers the real action itself, and
  the agent then runs the (client-initiated) CIBA flow and retries. This moves the
  un-bypassable trigger onto the resource server and lets the server define the
  approved action from the actual request. Targeted for the M4 build.

## Known residual risks (M2 scope)

- **Broker is a high-value single point of trust** (sole tuple writer + holds all
  refresh credentials). Mitigations above; hardening (rotation policy, mTLS
  between services, HA) is out of scope for the non-production reference.
- **Mock provider session lifespan** is stretched to 30 days for demo
  convenience; a production integration would use the real provider's refresh
  token, which the broker persists (including rotation) on each refresh.
