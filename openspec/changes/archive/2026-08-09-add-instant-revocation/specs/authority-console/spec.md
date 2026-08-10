# authority-console — delta (add-instant-revocation / M9)

## MODIFIED Requirements

### Requirement: Per-agent revoke from the console
The console SHALL offer per-agent consent revocation for the signed-in principal.
Revocation from the console SHALL converge on the same broker code path and audit
event as revocation from the consent surface, and SHALL invoke the M9 per-grant kill
(tuple delete + deny-list + revocation signal) — so effect is within seconds, not only
on the next hand-out, and re-acquiring the grant is blocked even with a fresh token. The
console SHALL report the measured time-to-stop and the honest in-flight residual to the
principal.

#### Scenario: One-click revoke tears up the delegation
- **WHEN** the principal revokes agent X's consent for provider P from the console
- **THEN** the `can_use` tuple is deleted, X's next provider-token request is
  refused 403, other agents are unaffected, and the register reflects the removal

#### Scenario: The revoke reports a measured kill time
- **WHEN** the principal revokes an agent from the console
- **THEN** the result states the measured new-authority-denied latency and the in-flight
  residual (the window in which an already-issued token remains valid), rather than a bare
  "effect on next hand-out" note
