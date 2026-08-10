# Design: add-instant-revocation (M9 — The kill switch)

## Context

M8 made revocation *legible* — a principal can tear up a delegation from the console. But
it is not yet *fast*. Three facts make "stop" slow today, confirmed against the live stack:

- The broker already re-checks the `can_use` tuple on **every** hand-out
  (`consent.is_allowed` in `issue_token`), so a deleted tuple denies the *next* hand-out
  immediately. That part is already instant.
- A provider access token **already issued** stays valid at the provider for its TTL
  (`MAX_TTL_SECONDS = 900`); Prokura cannot un-issue it (the mock `acme` provider has no
  revocation endpoint).
- The agent holds a user-bound token and, with `offline_access`, an **offline/refresh
  token** it can re-exchange to mint *fresh* authority — so deleting one tuple does not stop
  an agent that can re-acquire tokens.

So "instant revocation" is really three moves: deny the *next* hand-out (done), stop the
agent from **re-acquiring** authority (Keycloak session/offline revocation), and provide a
propagation-free **explicit stop** with an honest report of the only residual Prokura can't
shorten (the in-flight token's remaining TTL). Constraints carried from prior milestones:
the broker stays the sole `can_use` writer under the owner invariant; honest TTL (ADR-0003);
demo-grade infrastructure; verified by looking + measured against the real sinks.

## Goals / Non-Goals

**Goals:**

- A single owner-authenticated revoke fans out across every path that can stop an agent and
  reports a **measured** time-to-stop with an honest in-flight residual.
- Every broker hand-out re-evaluates a deny-list in addition to the consent tuple.
- The agent cannot re-mint authority after revoke (Keycloak sessions + offline tokens gone).
- Revocation is emitted as a standards-track **CAEP/SSF** Security Event Token.
- Exit: "how fast can you make an agent stop?" answered with a number, on the dashboard.

**Non-Goals:**

- **CIBA push mode** — serves approval latency, not the stop-an-agent exit; deferred.
- Real provider-side token revocation (mock `acme` has none) — the residual is reported
  honestly and closed for real Google/GitHub in M12.
- A production multi-receiver SSF deployment — the transmitter is demo-grade (one stream).
- Risk tiers / standing approvals / budgets (M11).

## Decisions

### D1 — Two grains: a scoped per-grant revoke and a broader agent-wide kill

A new `services/token-broker/revocation.py` distinguishes two revoke grains — a distinction
that surfaced during implementation and matters for correctness:

- **`kill(agent, user, provider)` — per-grant revoke** (what the console/consent-surface
  button does): (1) delete the `can_use` tuple; (2) write a **deny-list** entry for that
  grant; (3) emit a CAEP SET (D4); return timing + residual. It is instant and **scoped** —
  the agent's Keycloak session and its *other* consented grants are untouched. Re-acquiring
  **this** grant is blocked even with a brand-new user token, because the deny-list denies
  before the provider is contacted, so no Keycloak session revocation is needed to protect
  the revoked grant.
- **`kill_agent(agent, user)` — the agent-wide kill**: an agent-wide (null-provider) deny
  entry, delete of *every* `can_use` tuple the agent holds on the user's grants, **and**
  Keycloak session/offline revocation for the agent client (D3), so the agent cannot
  re-acquire *any* authority. This de-delegates the agent entirely; the human's own sessions
  are never touched. It is the "stop this agent everywhere" move.

Deleting the agent's Keycloak `act-on-your-behalf` consent (D3) de-delegates it for *all*
grants — correct for an agent-wide kill, but wrong for a per-grant revoke (it would revoke
grants the user did not ask to touch, and break the agent's other consents). So the KC move
lives only in `kill_agent`. Both are broker functions under the owner invariant; the broker
stays the single actor on authorization state.

*Alternative — fold KC revocation into every per-grant revoke:* rejected during
implementation; it violates per-grant scoping ("revoke one grant without disturbing the
others") and the deny-list already blocks re-acquiring the revoked grant. *Alternative — a
standalone revocation service:* rejected; it would split ownership of authorization state
away from the broker for no benefit at demo scale.

### D2 — Continuous evaluation: a deny-list checked on every hand-out + bounded TTL

The hand-out chain gains one step: after the consent-tuple check, refuse if a deny-list
entry matches (before contacting the provider). The deny-list is a Postgres table
`broker_denylist(agent, user_id, provider NULL, reason, azp, created_at)` — `provider = NULL`
means "this agent for this user, all providers" (the true *kill switch*, broader than a
single-grant revoke). It is the **propagation-free explicit stop**: independent of any FGA
read consistency, it denies immediately and carries the reason for audit + CAEP. The
consent tuple remains the durable consent *state*; the deny entry is the fast, broad *stop*.
Provider-token TTL is bounded to a small residual (`MAX_TTL_SECONDS` lowered, e.g. 120 s,
tuned by the spike) so the only window Prokura can't shorten is small and **reported**.

*Alternative — rely on the tuple delete alone:* rejected; the tuple is per-grant and its
delete is a single mutation with no reason/breadth, and it does not stop token
re-acquisition. The deny-list adds breadth (agent-wide), a reason, and a propagation-free
guarantee. *Alternative — TTL = a few seconds:* rejected; too many provider refreshes;
120 s is an honest, demo-legible floor and the spike measures the trade.

### D3 — Keycloak session + offline-token revocation, so the agent can't re-acquire

The load-bearing instant-revocation move. Even with the tuple gone and a deny entry, the
agent's offline/refresh token would let it mint *new* user-bound tokens. The broker (via a
confidential admin-capable client — service account with the **minimal** role the spike
proves) revokes the agent client's offline sessions/consent **for this user only**, not the
human's own sessions. The leading candidate (spike validates the exact API + role) is
deleting the user's consent for the agent client
(`DELETE /admin/realms/{realm}/users/{id}/consents/{agent-client}`), which drops that
client's offline sessions; a fallback is per-session logout filtered to the agent client.
After this, a re-exchange as the agent for this user fails — the agent is *stopped at the
source*, not merely denied at the broker.

*Alternative — short TTL + deny-list only, skip Keycloak:* rejected; `offline_access`
persistence is precisely the durable-authority risk, and the roadmap names Keycloak
session/offline revocation explicitly. *Alternative — full user logout:* rejected; nuking
the human's own sessions to stop one agent is collateral damage — revocation is scoped to
the agent client for that user.

### D4 — A demo-grade CAEP/SSF transmitter

On kill, the broker builds a **Security Event Token** (signed JWT) carrying a CAEP
`session-revoked` (subject = the agent acting for the user, plus grant context) and delivers
it to registered receivers. Demo-grade: an in-memory subscriber list and a `GET /ssf/stream`
poll endpoint (RFC 8935 push is a stretch), the SET logged to the audit stream so it is
Loki-queryable and joinable to the revoke trace. Signing reuses the broker's confidential
client key material (spike confirms; a self-signed broker key is the fallback).

*Alternative — no CAEP, just the internal tuple delete:* rejected; "revocation becomes a
signal other systems can consume" is thesis #3's standards-track half — the demo emits a
real SET, honestly labeled single-stream.

### D5 — Measure and surface "time to stop" (the exit)

`kill()` timestamps each leg (t0 revoke received → tuple gone → Keycloak revocation done →
deny active) and computes: **new-authority-denied** = when the agent can no longer *obtain
or be issued* authority (≈ the max of the Prokura-mediated legs, sub-second), and the
**in-flight residual** = the remaining TTL of any token already in the agent's hand (≤ the
bounded TTL). The console shows both to the principal ("new authority denied in *X* ms; any
token already issued expires within ≤ *N* s"); the operator dashboard gets a **time-to-stop**
panel fed by a `prokura.revocation.stop_ms` metric, joinable to the revoke's trace + audit
line. This honesty — an instant Prokura-mediated stop plus a small, named residual — is the
integrity of the answer, not a caveat to hide.

### D6 — Spike-first: measure the three paths + the residual before building

`spike/kill-switch/` drives the live stack and records: (a) consent revoke → time to the
first denied hand-out; (b) Keycloak session/offline revoke → time until a re-exchange as the
agent fails (and which API + minimal admin role achieves it without touching the human's
sessions); (c) deny-list add → time to a refused hand-out; (d) the in-flight residual —
issue a provider token, revoke everything, confirm it still works at the mock provider until
its (now-bounded) TTL. The measured numbers and the proven Keycloak API/role land in this
doc before the deny-list, TTL bound, and admin client are designed into the realm.

## Risks / Trade-offs

- [Broker holding an admin-capable Keycloak client widens its blast radius] → the service
  account gets the **single minimal role** the spike proves (targeted consent/offline
  revocation for a client, not `realm-admin`); scoped to revoking an agent client for a
  user, never the human's own sessions; audited with azp on every call.
- [Shrinking provider-token TTL increases provider refresh load] → 120 s is a demo-legible
  floor; the spike reports the trade; real deployments tune it against provider rate limits.
- [The in-flight residual can't be zero without provider revocation] → reported honestly on
  the console and dashboard; closed for real providers in M12; the mock `acme` has no
  revocation endpoint, so pretending otherwise would be dishonest.
- [Deny-list drift from the consent tuple] → both are checked in the same hand-out step and
  written by the same `kill()`; a smoke test asserts a killed agent is refused by *both* the
  tuple check and the deny-list, and that re-consent clears the deny entry.
- [Demo-grade in-memory SSF stream loses events on restart] → stated as a residual; the SET
  is also in the durable audit stream (Loki), so the signal is not lost, only the live push.

## Migration Plan

Additive and clean-slate friendly: new `broker_denylist` table (idempotent DDL at startup),
new broker endpoints (`kill` fan-out is internal to the two revoke handlers; `/ssf/stream`
is new and read-only), a new confidential admin-capable broker client + minimal role in
`realm-export.json` (re-imports on a clean `docker compose up`), and a lowered
`MAX_TTL_SECONDS`. All M7/M8 paths remain; revoke gains speed, not a new contract shape
(the console/surface revoke request bodies are unchanged). Rollback = git revert + clean
compose up.

## Spike findings (`spike/kill-switch/kill_spike.py`, run against the live stack)

- **(a) tuple delete is already ~instant.** Deleting the `can_use` tuple denies the next
  broker hand-out in **~36 ms** (FGA propagation), confirming M8's per-hand-out check is
  effectively instant for *future* hand-outs. The deny-list is therefore not about the
  tuple path's speed but about **breadth** (agent-wide, null-provider), a **reason** record,
  and a propagation-free guarantee that doesn't depend on FGA read state.
- **(b) the load-bearing move is a targeted consent delete — CONFIRMED.**
  `DELETE /admin/realms/{realm}/users/{id}/consents/agent-app` → **204**, after which the
  agent's refresh (`grant_type=refresh_token`) returns **`400 invalid_grant`** — the agent
  is stopped at the source and cannot re-mint. The human's interactive sessions are
  **untouched** (3 → 3): this is scoped to the agent *client* for that user, not a user
  logout. It revokes the client's **online and offline** refresh alike (agent-app is not
  even granted `offline_access`, yet its online refresh is killed), so it is the complete
  mechanism regardless of token kind. **Minimal role:** the broker's service account needs
  realm-management **`manage-users`** to delete a user's client consent (task 2.1) — broad
  enough to manage user consents, far short of `realm-admin`; audited with azp on every call.
- **(c) the in-flight residual is real and must be honest.** A provider (acme) access token
  issued moments before revoke still validates at acme's `userinfo` **after** revoke (200),
  because the mock provider has no revocation endpoint. It stays valid until its TTL — today
  the broker's `expires_in=900`. M9 **bounds this to a small floor (120 s default)** and
  **reports** the residual on revoke rather than pretending a provider token was killed.

## Open Questions (resolved / remaining)

- ~~Exact Keycloak API + minimal role~~ **Resolved:** `DELETE users/{id}/consents/{agent-client}`
  (204), realm-management `manage-users`; kills online + offline refresh; human sessions
  untouched (spike b).
- ~~Honest provider-token TTL floor~~ **Resolved:** 120 s default (residual is otherwise the
  full 900 s; spike c). Configurable; real deployments tune against provider rate limits.
- SET signing key: reuse a broker realm-client key vs a self-signed broker key — deferred to
  build (self-signed broker key is the low-risk default for the demo SSF stream).
