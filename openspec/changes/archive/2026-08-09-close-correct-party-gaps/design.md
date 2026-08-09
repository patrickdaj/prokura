# Design: close-correct-party-gaps (M7)

## Context

Every trusted surface in v0 authenticates via a bearer token a demo driver puts in the
URL (`approval.html?token=`, `consent.html?token=`), and the CIBA ceremony can only be
initiated by the in-repo `agent-app` confidential client — so the human's capacities in
Flows B and C are, in practice, always played by scripts, and a real external agent
either cannot drive Flow C at all or drives it by impersonating everyone (observed live,
2026-08-08). The gap table is in `docs/architecture.md` §"Correct-party gaps". M7
re-wires *who does what* without changing what is enforced: hash-binding, single-use,
sole-writer, and audience rules all stay exactly as shipped (F5-A, F8-A, F1-A, F2-A).

## Goals / Non-Goals

**Goals:**

- The agent's role in Flow C is exactly: receive `428` → wait → retry with
  `action_token`. Nothing else is *possible* from the agent's position.
- A human can complete every human capacity (approval decision, per-agent consent) in an
  authenticated browser session reached from the notification deep link, with zero
  URL-carried credentials.
- Headless agent bootstrap exists that never touches a user password (RFC 8628).
- Simulated humans in tests are quarantined to one explicitly-labeled UI-driving kit that
  exercises the *real* login + UI path; agent-side kits hold no user credentials.
- SR-01, SR-02, and RAG tuple reconciliation closed.

**Non-Goals:**

- The authority console (M8) — M7 upgrades the two existing surfaces in place; no
  aggregation, no revoke UX, no notification onboarding.
- Instant revocation (M9), CIBA push mode (M9), risk tiers / org routing (M11).
- Real providers (M12); the acme realm remains the provider stand-in.
- Production session hardening beyond the demo-grade bar (no Redis session store, no
  CSRF framework beyond SameSite + state).

## Decisions

### D1 — The approval service initiates CIBA, at registration time

On `POST /register` (which the tools-API calls when it fires the 428), the approval
service itself calls Keycloak's `/ext/ciba/auth` with `login_hint` = the registered
user, `binding_message` = the new `ref`, using its own confidential client
(`approval-service`, CIBA grant enabled, poll delivery mode). It stores `auth_req_id`
alongside the approval row and completes the ceremony (polls the token endpoint after a
decision; discards the issued token — the *ceremony* is the product, the token has no
consumer).

*Why here and not the MCP server:* the approval service already owns every other leg of
the ceremony (register → `/ciba/delegate` callback → decide → relay to Keycloak's
callback). Initiation from the MCP server would (a) duplicate ceremony ownership across
two services, (b) leave non-MCP callers of the tools-API stuck, and (c) put CIBA client
credentials outside the approval service's trust position for no gain. With D1 the MCP
server's 428 relay needs **zero changes** — the ceremony simply no longer involves the
agent side at all. `agent-app` loses the CIBA grant in `realm-export.json`
(**BREAKING** for `approvalkit.ciba_init`, deliberately: that path must die).

*Alternative considered:* keep client-initiated CIBA and provision per-DCR-client CIBA
grants. Rejected — hands the ceremony to the least-trusted party (the agent), which is
the root cause being fixed, and anonymous DCR clients are public (no client auth for the
backchannel grant anyway).

### D2 — Per-surface OIDC session: Authorization Code + PKCE, cookie session, one small shared module pattern

Both surfaces gain a real login: `GET /approvals` and `GET /consent` redirect to
Keycloak (auth-code + PKCE, confidential clients `approval-ui` / `broker-ui` baked into
`realm-export.json` with exact redirect URIs), callback sets a signed, HttpOnly,
SameSite=Lax session cookie holding `{sub, preferred_username, exp}`; session lifetime
mirrors the SSO session (≤ the realm's session max, not the 15-min token TTL — the
*token* honesty rule is about delegated tokens, not first-party browser sessions).
Decide/consent POSTs authorize against the session identity: `approval.user_id ==
session.sub` for decisions; `operator == owner` for consent writes now takes the owner
from the session, closing the loop on the F1-A/Q3-B write-guard.

Implementation follows the repo's per-service-module convention (each service already
carries its own `audit.py`/`telemetry.py`): a small `websession.py` replicated into
`services/approval/` and `services/token-broker/`, proven first in
`spike/surface-session/` (the M7 spike; the pattern is what M8's console will reuse).

### D3 — Deep link stays capability-free; the fragment survives login via `state`

The ntfy link remains `/approvals#<ref>` (ADR-0007 unchanged: notify-only, no
capability). Page JS stashes the ref before redirecting to login and the OAuth `state`
round-trips it (fragments never reach the server), so post-login the user lands on the
rendered approval. No-session + no-ref renders the existing graceful zero state.

### D4 — Device Authorization Grant for headless bootstrap

Enable OAuth 2.1 device flow on the realm and on `agent-app`; a browserless agent prints
`verification_uri_complete` + user code and polls. The human approves in their own
browser session on a second surface — same consent screen as Flow A (D5). Smoke tests
bootstrap headless-agent tokens this way; `drive_login`'s password-holding path is
removed from agent-side kits.

### D5 — Consent scope becomes a realm fixture

`act-on-your-behalf` (display-on-consent-screen scope + `consentRequired`) moves from
`flow_a.py` live-configuration into `realm-export.json`, applied per-client
(`agent-app`, and the DCR registration policy for MCP clients — which already forces
`consentRequired` per the anonymous-DCR policy; the scope makes the *delegation* text
explicit). `flow_a.py` drops its `configure_consent` mutation and just drives the flow.

### D6 — Quarantined human simulation in tests

New `tests/smoke/humankit.py` (Playwright): logs in via the real Keycloak page, drives
the real surfaces (`/approvals`, `/consent`, device verification) as a labeled
**simulated human** — correct in *mechanism*, simulated in *actor*, which CI requires.
Agent-side kits (`approvalkit`, `brokerkit`, `mcpkit`) lose `decide()`, `consent()`,
`ciba_init()`, and every use of `DEMO_PASSWORD`. A grep-able invariant test asserts no
agent-side kit imports credentials or hits `/decide`, `/consent`, or `/ext/ciba/auth`.

### D7 — Hardening debt

- **SR-01:** upstream error text never echoed; services map to
  `{error: <stable-code>}` and log the detail server-side (audit line only).
- **SR-02:** `/ciba/delegate` authenticated by verifying the delegation bearer
  itself, plus a body-size cap; unauthenticated callers get 401 before any parse.
  *(Amended by spike finding S4: the built-in HTTP-channel SPI has no
  shared-secret-header config, and none is needed — Keycloak already
  authenticates each delegation POST with a realm-signed JWT.)*
- **RAG reconciliation:** `services/rag/ingest.py` separates tuple-sync from the
  pgvector seed guard — on startup, read the manifest, `batch_check` the expected
  owner/viewer tuples, write any missing (idempotent), regardless of vector-seed state.

## Spike findings (task 1.4, run 2026-08-09 against the live stack)

- **S1 — Session pattern proven.** Auth-code + PKCE with a confidential client →
  HMAC-signed HttpOnly SameSite=Lax cookie holding `{sub, preferred_username, exp}`
  works end-to-end over httpx-driven login; tampered and absent cookies are refused.
  The `#ref` fragment survives the round-trip inside the signed `state`
  (`spike/surface-session/websession.py` is the module that graduates into the
  services).
- **S2 — Cookie coexistence confirmed.** Two surfaces on `localhost:8961/8962` with
  distinct cookie names (`prokura_<surface>_session`) coexist in one jar; the
  second login is form-less (Keycloak SSO session covers both surfaces — the
  deep-link UX benefits: one login serves approval + consent).
- **S3 — Server-initiated CIBA proven whole.** A service-held confidential client
  (CIBA grant, poll mode) initiated with `login_hint=alice`,
  `binding_message=<real ref>`; Keycloak delivered the delegation to the live
  `/ciba/delegate`; decide → poll returned a token with `sub=alice`,
  `azp=<service client>`. The agent side did nothing. Token discarded.
- **S4 — SR-02 mechanism corrected.** The built-in `ciba-http-auth-channel` SPI
  offers only the URI config — no shared-secret header. But every delegation POST
  already carries `Authorization: Bearer <realm-signed RS256 JWT>`
  (`iss=<realm>`, `azp=<initiating client>`). `/ciba/delegate` therefore
  authenticates by verifying that JWT (signature + issuer, and `azp` must be the
  approval service's own CIBA client once D1 lands) before parsing, with a
  body-size cap. Stronger than the planned shared secret.
- **S5 — `cibaExpiresIn` clamp behavior.** The realm attribute is the effective
  value: with `cibaExpiresIn=600`, `expires_in=600` comes back even when
  `requested_expiry=300` is sent (Keycloak overrides rather than min()s). Realm
  fixture sets **600 s** — human-latency decisions fit; the old 30 s clamp was
  agent-latency thinking.

## Risks / Trade-offs

- [Keycloak's CIBA grant may reject a client without backchannel auth or clamp
  `cibaExpiresIn` (30 s realm clamp found in M3)] → the M7 spike phase re-validates the
  full server-initiated ceremony against the real realm before any service code changes;
  the 30 s clamp may need raising for human-latency decisions (realm setting, honest in
  docs).
- [Session cookie on `localhost` across two ports (8120/8110) can confuse browsers
  (cookie scoping is host-wide, not port-wise)] → distinct cookie names per service;
  spike verifies both sessions coexist.
- [Playwright-driven login in CI is slower and flakier than token calls] → humankit used
  only where a human capacity is the thing under test; pure-mechanism tests (hash
  mismatch, replay, single-use) keep driving service APIs directly with *service*
  — not user — credentials.
- [Removing `agent-app`'s CIBA grant breaks any v0 walkthrough that scripted the old
  ceremony] → walkthroughs are static recreations (no live dependency); the M7 blog
  documents the contract change.
- [State-carried ref adds an open-redirect-shaped surface] → `state` is signed and the
  post-login redirect is fixed to the surface's own path; ref is validated
  `^apr-[0-9a-f]+$` before use.

## Migration Plan

Realm changes land first (new clients, device flow, consent fixture, CIBA client swap) —
`realm-export.json` is re-imported on `docker compose up` from clean state, which is the
project's supported reset path (non-production stance). Service changes are additive
until the final task removes the `?token=` paths and `agent-app`'s CIBA grant; smoke
suite must be green at that cut, which is the point of no return for the old ceremony.
Rollback = git revert + clean compose up.

## Open Questions

- Should the discarded CIBA-issued token instead be *used* as the decide-relay
  credential internally (tighter binding, more moving parts)? Default: discard; revisit
  in M9 when push mode replaces polling.
- Does the Keycloak 26 device-flow consent page render the `act-on-your-behalf` scope
  text without theming work? If not, accept default text for M7 (theming is M8-adjacent
  polish).
