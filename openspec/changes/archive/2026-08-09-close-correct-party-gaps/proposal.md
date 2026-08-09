# Proposal: close-correct-party-gaps (M7 — Correct parties)

## Why

v0's flows are architecturally correct about who holds which authority, but operationally
the human's capacities are filled by scripts: every trusted surface (`approval.html`,
`consent.html`) authenticates via a bearer token passed in the URL by a demo driver, and a
real external agent cannot even initiate CIBA (the backchannel grant requires the in-repo
`agent-app` confidential client). Discovered live on 2026-08-08 when an agent driving the
stack completed a CIBA approval *itself* with in-repo dev credentials — the exact
self-authorization Prokura exists to prevent. Until the correct parties are present in
each capacity, no downstream v1 work (console, revocation, gateway) can be demonstrated
honestly. Full analysis: `docs/architecture.md` §"Correct-party gaps — the forcing
function for v1".

## What Changes

- **Server-initiated CIBA (reactive step-up completes ADR-0018):** on a `428
  approval_required`, the MCP server (not the agent) initiates the CIBA ceremony using its
  own client and `login_hint` derived from its *verified* claims. The agent's role shrinks
  to: receive 428 → wait → retry with `action_token`. Removes the agent from the approval
  ceremony entirely (extends the F5-A/F8-A chain of custody to initiation).
- **Real OIDC sessions on the trusted surfaces:** `approval.html` and `consent.html` gain
  a Keycloak Authorization Code + PKCE login (session cookie), replacing `?token=` in the
  deep link. The ntfy deep link becomes actually followable by a human (ADR-0007's
  notify-only stance unchanged).
- **Persist the delegation consent scope:** bake the `act-on-your-behalf` consent-screen
  scope into `realm-export.json` per-client (today `demo/capture/flow_a.py` configures it
  live), so Flow A's explicit consent survives a cold `docker compose up`.
- **Headless bootstrap without user passwords:** enable Device Authorization Grant
  (RFC 8628) on the realm so a browserless agent delegates via a user code approved on a
  second device; test code stops holding `alice`'s password for bootstrap.
- **Hardening debt:** SR-01 (error-text leak) and SR-02 (unauthenticated `/ciba/delegate`
  DoS bound) from `docs/security-review.md`; RAG owner/viewer tuple reconciliation on
  startup (OpenFGA store reset after first ingest currently leaves every document
  silently filtered).

## Capabilities

### New Capabilities

(none — M7 corrects party presence within existing capabilities)

### Modified Capabilities

- `human-approval`: approval trigger AND ceremony initiation move server-side (428 →
  server-initiated CIBA); the trusted approval UI requires an authenticated Keycloak
  session instead of a URL-carried token; decisions only in that session.
- `mcp-authorization`: the `send_email` challenge contract changes — the MCP server
  initiates CIBA on 428 and returns only `{ref, action_token, status}`; agents are never
  instructed to (and cannot) drive the ceremony.
- `per-agent-consent`: the consent screen requires an authenticated Keycloak session;
  `can_use` tuples are written only from a session belonging to the grant owner (F1-A/Q3-B
  write-guard now enforced by a real session, not a script-held token).
- `identity-delegation`: the explicit "act on your behalf" consent scope is a persisted
  realm fixture; Device Authorization Grant is a supported delegation mode for headless
  agents (SPEC.md §10 item pulled forward).
- `security-baseline`: SR-01 and SR-02 move from "logged findings, deferred" to fixed
  invariants.
- `rag-authorization`: ingestion's FGA tuple writes are reconciled on startup,
  decoupled from the pgvector seed guard.

## Impact

- `services/mcp/` — CIBA initiation in the 428 path of `tools.py`; new Keycloak client
  credentials/config for the backchannel grant.
- `services/approval/` — session middleware + OIDC login on `/approvals`; SR-02 bound on
  `/ciba/delegate`; `approval.html` loses `?token=`.
- `services/token-broker/` — session middleware + OIDC login on `/consent`;
  `consent.html` loses `?token=`.
- `deploy/keycloak/realm-export.json` — consent scope fixture, device-flow realm settings,
  MCP-server client grant for CIBA initiation.
- `services/rag/ingest.py` — tuple reconciliation on startup.
- `tests/smoke/` — `approvalkit`/`brokerkit`/`mcpkit` reshaped: the simulated-human path
  is quarantined to explicitly-labeled UI-driving helpers (Playwright against the real
  login), and the agent-side helpers lose all user credentials.
- `demo/capture/flow_a.py` — consent-scope live-config removed (now a realm fixture).
- Docs: architecture gap table gets closure checkmarks; threat-model Flow C note
  (agent-influenceable trigger) resolves; M7 blog.
