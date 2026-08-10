# Proposal: add-instant-revocation (M9 — The kill switch)

## Why

"How fast can you make an agent stop?" is the first question a security team asks, and
today Prokura's honest answer is "up to ~15 minutes." M8 lets a principal revoke a
delegation, but the console says so itself: *effect applies on the agent's next token
request*. Three gaps make revocation slow: a provider access token already handed out
stays valid for its full TTL (≤900 s); the agent can mint **fresh** user-bound tokens
from its `offline_access`/refresh token and re-exchange to keep going; and there is no
propagation-free "stop now" nor any way for another system to consume the revocation as a
signal. Instant, continuously-evaluated revocation is thesis #3 and the emotional climax
of the v1 spine (`docs/architecture.md` §"Beyond parity" #3, §"v1 delivery plan — M9").

## What Changes

- **New capability `revocation`** — a **kill switch** that, on a single revoke, fans out
  across every path that can stop an agent and reports the *measured* time-to-stop:
  1. delete the `can_use` tuple (already denies the next broker hand-out);
  2. revoke the agent's **Keycloak sessions + offline/refresh tokens** so it can obtain no
     new user-bound authority to exchange;
  3. add a broker **deny-list** entry (agent · grant, and agent · user) checked before
     every hand-out — a propagation-free "stop now" independent of tuple/JWKS timing.
- **Continuous evaluation on every hand-out** — the broker's hand-out chain SHALL
  re-evaluate the deny-list in addition to the consent tuple, and provider-token TTLs are
  bounded to a small, honestly-reported residual (the only window Prokura cannot shorten
  further without provider-side revocation, which the mock `acme` provider lacks — noted
  as a residual, closed for real providers in M12).
- **A Shared Signals / CAEP emitter** — revocation is emitted as a standards-track
  Security Event Token (`session-revoked` / `token-claims-change`) to a subscribable
  stream, so revocation and risk become signals other systems can consume, not just an
  internal tuple delete.
- **The console reports the kill time** — the authority console's revoke triggers the
  full kill path and surfaces a measured "time to stop" (and the honest in-flight
  residual); the operator dashboard gets a time-to-stop panel.
- The broker's write-guard, the sole-writer invariant, and M8's exchanged-bearer relay are
  unchanged; the kill fan-out is performed by the broker under the same owner invariant.

## Capabilities

### New Capabilities

- `revocation`: the kill switch — the revoke fan-out (tuple + Keycloak session/offline
  revocation + broker deny-list), continuous per-hand-out evaluation, the CAEP/SSF signal
  emission, and the measured, surfaced "time to stop" guarantee with an honest in-flight
  residual.

### Modified Capabilities

- `token-brokering`: the hand-out chain SHALL additionally refuse any request matching a
  broker deny-list entry (checked before provider issuance), and provider-token TTL is
  bounded so the post-revocation in-flight window is small and reported. (The existing
  consent-tuple check and validation chain are unchanged.)
- `per-agent-consent`: consent revocation SHALL take effect within seconds rather than
  only on the next hand-out — the same owner-authenticated revoke additionally revokes the
  agent's Keycloak sessions/offline tokens, writes a broker deny entry, and emits a
  revocation signal; both revoke paths (surface + console) converge on the extended path.
- `authority-console`: the console's revoke SHALL invoke the kill switch and report the
  measured time-to-stop and the honest in-flight residual to the signed-in principal.
- `observability`: a "time to stop" measurement SHALL be recorded per revocation and
  surfaced on the operator dashboard (and joinable to the revoke's trace/audit line).

## Impact

- New: `services/token-broker/revocation.py` (the kill fan-out + deny-list + KC revocation
  + CAEP emit), broker deny-list store (Postgres table, checked in the hand-out chain), a
  minimal CAEP/SSF transmitter endpoint (`/ssf/stream`, in-memory subscribers — demo-grade).
- Modified: `services/token-broker/` (hand-out chain deny-list check, TTL bound, revoke
  fan-out), `services/authority/` (revoke reports kill time + residual; panel copy),
  `deploy/keycloak/realm-export.json` (whatever the spike proves is needed for the broker
  to revoke an agent's sessions/offline tokens — admin reach or the token-revocation
  endpoint), console/dashboard (`services/console`, LGTM dashboard) time-to-stop panel.
- Tests: `tests/smoke/test_revocation.py` (kill-time measurement, offline-token can't
  re-mint after revoke, deny-list refuses in-flight re-issuance, CAEP event emitted); the
  M8 revoke-parity and separation invariants must keep passing.
- Docs: `revocation` spec; architecture "kill switch" row; **M9 blog**
  (`docs/blog/m9-instant-revocation.html`); **walkthrough** (`docs/walkthroughs/revocation.html`)
  with live screenshots; new ADR (the kill fan-out + the honest in-flight residual).
- Spike-first (same discipline as M7/M8): **measure the propagation latency of the three
  revocation paths** (tuple-delete → denied hand-out; Keycloak session/offline revocation →
  exchange fails; deny-list → refused) and the in-flight-token residual against the live
  stack, before designing the deny-list and TTL bound.

## Non-Goals

- **CIBA push mode** (delivery-mode change for approvals) — listed under M9 in the roadmap,
  but it serves *approval* latency, not the *stop-an-agent* exit; deferred to keep this
  change focused on the revocation triad and its measured number. Noted in design.
- Real provider-side token revocation (the mock `acme` has none) — the in-flight residual
  is reported honestly here and closed for real Google/GitHub in M12.
- Risk-tiered / standing approvals / budgets (M11); a full multi-receiver SSF deployment
  (the emitter is demo-grade, one in-memory stream).
