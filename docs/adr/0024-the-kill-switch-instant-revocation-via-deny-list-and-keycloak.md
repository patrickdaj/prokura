# ADR-0024: The kill switch — instant revocation via a deny-list, an agent-wide Keycloak kill, and an honest residual

- **Status:** accepted
- **Source of truth:** `openspec/changes/archive/*-add-instant-revocation/`; `services/token-broker/revocation.py`
- **Relationship:** Builds on the per-hand-out consent check of ADR-0012/ADR-0001 (the broker re-checks `can_use` on every hand-out) and the M8 revoke relay (ADR-0023); honours honest-TTL (ADR-0003). Answers "how fast can you make an agent stop?" for the v1 spine.

## Context

After M8 a principal can revoke a delegation, but the honest answer to *when* it takes
effect was "the agent's next token request" — and, in the worst case, up to the full
provider-token TTL (900 s). The broker already denies the **next** hand-out the instant the
`can_use` tuple is gone (~36 ms, measured). What remained were two gaps: a provider access
token **already issued** stays valid at the provider until its TTL (the mock `acme` provider
has no revocation endpoint), and an agent holding a refresh/offline token could mint **fresh**
user-bound tokens and re-exchange. "How fast can you make an agent stop?" is the first
question a security team asks; v1 must answer it with a measured number, honestly.

An implementation subtlety forced a design decision: revoking the agent's Keycloak
`act-on-your-behalf` consent (which kills its refresh/offline tokens) **de-delegates the
agent for all grants**. That is correct when you want to stop an agent entirely, but wrong
for a *per-grant* revoke — it would disturb grants the user did not ask to touch.

## Decision

Two grains of revoke, both broker functions under the owner invariant:

- **Per-grant revoke** (`kill`, what the console/consent-surface button does): delete the
  `can_use` tuple, write a **deny-list** entry for that grant, and emit a CAEP signal. It is
  instant and **scoped** — the agent's Keycloak session and its *other* grants are untouched.
  Re-acquiring the revoked grant is blocked even with a brand-new user token, because the
  deny-list is checked on **every** hand-out before the provider is contacted, independent of
  OpenFGA read consistency. So no Keycloak session revocation is needed to protect the
  revoked grant. The broker reports a **measured `stop_ms`** (new-authority-denied latency,
  low tens of ms) and the **honest in-flight residual** — the ≤ TTL window in which an
  already-issued provider token stays valid, which the provider (not Prokura) controls.
- **Agent-wide kill** (`kill_agent`): an agent-wide (null-provider) deny entry, deletion of
  every `can_use` tuple the agent holds on the user's grants, **and** revocation of the agent
  client's Keycloak sessions + offline/refresh tokens for that user
  (`DELETE users/{id}/consents/{agent-client}`, spike-proven → refresh `400 invalid_grant`),
  so the agent cannot re-acquire *any* authority. Scoped to the agent client — the human's
  own sessions are never touched (no user logout). The broker's service account holds exactly
  realm-management **`manage-users`** for this, far short of `realm-admin`.

Provider-token TTL is bounded to a small floor (120 s default) so the in-flight residual is
small and legible. Revocation is emitted as a signed CAEP `session-revoked` Security Event
Token to a demo SSF stream (`/ssf/stream`) and the realtime audit log, so it is a signal
other systems can consume. The measured `stop_ms` is a metric on the operator dashboard.

## Alternatives considered

- **Fold Keycloak session revocation into every per-grant revoke.** Rejected during
  implementation: it de-delegates the agent for all grants (breaking "revoke one grant
  without disturbing the others") and is unnecessary — the deny-list already blocks
  re-acquiring the revoked grant with a fresh token.
- **Rely on the tuple delete alone.** Rejected: it is per-grant with no breadth or reason,
  depends on FGA read state, and does not express an agent-wide stop. The deny-list adds a
  propagation-free guarantee, agent-wide scope, and a reason for audit/CAEP.
- **Shrink provider TTL to a few seconds to erase the residual.** Rejected: too many provider
  refreshes; 120 s is an honest, legible floor. The residual is disclosed, not hidden —
  pretending a mock-provider token was revoked when it wasn't would be dishonest.
- **Full user logout to stop an agent.** Rejected: nuking the human's own sessions to stop
  one agent is collateral damage; the kill targets the agent client for that user only.

## Consequences

"How fast can you make an agent stop?" now has a number: new authority is denied in **low
tens of milliseconds** (tuple + deny-list), the agent-wide kill additionally revokes the
agent's Keycloak refresh so it cannot re-acquire, and the only residual is a small, **named**
in-flight window the provider controls (closed for real providers in M12, where GitHub/Google
support token revocation). The broker gains one admin-capable role (`manage-users`), used only
to revoke an agent client's consent for a user — a widened blast radius noted in the residual
register. The SSF transmitter is demo-grade (single in-memory stream, HS256); the SET also
lands in the durable audit stream. Delivered in M9.
