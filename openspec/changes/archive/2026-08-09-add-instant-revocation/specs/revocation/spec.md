# revocation — new capability (add-instant-revocation / M9)

## ADDED Requirements

### Requirement: Per-grant revoke fan-out
A single owner-authenticated per-grant revoke SHALL, under the owner invariant, delete the
`can_use` consent tuple, write a broker deny-list entry for that grant, and emit a
revocation signal — instantly and **scoped**: the agent's Keycloak session and its other
consented grants SHALL be untouched. The fan-out SHALL be performed by the broker (the sole
writer of authorization state); both existing revoke paths (the M7 consent surface session
and the M8 authority console exchanged bearer) SHALL converge on it.

#### Scenario: One revoke stops the agent on the revoked grant
- **WHEN** the owner revokes agent X for provider P
- **THEN** the `can_use` tuple is deleted, a deny-list entry exists for X on P, a revocation
  signal is emitted, X's next request for P is refused, and X's other grants are unaffected

#### Scenario: Re-acquiring the revoked grant is blocked even with a fresh token
- **WHEN** a revoked agent obtains a brand-new user-bound token and requests the revoked
  grant again
- **THEN** the broker refuses before contacting the provider (the deny-list denies it), so a
  fresh token is no re-acquisition path — no Keycloak session revocation is required to
  protect the revoked grant

### Requirement: Agent-wide kill revokes Keycloak sessions so the agent cannot re-acquire
An agent-wide kill SHALL stop an agent entirely for a user: an agent-wide (null-provider)
deny entry, deletion of every `can_use` tuple the agent holds on the user's grants, and
revocation of the agent client's Keycloak sessions and offline/refresh tokens **for that
user**, so the agent cannot obtain a new user-bound token to re-acquire any authority. It
SHALL be scoped to the agent client — the human's own browser/SSO sessions SHALL be
unaffected.

#### Scenario: Killed agent cannot re-acquire any authority
- **WHEN** an agent is killed agent-wide and then presents its offline/refresh token to mint
  a fresh user-bound token for that user
- **THEN** the refresh is refused, so the agent cannot re-acquire authority for any grant

#### Scenario: The kill is scoped to the agent, not the human
- **WHEN** the agent-wide kill revokes the agent client's sessions/offline tokens
- **THEN** only the agent client's sessions for that user are revoked; the human's own
  browser/SSO sessions are unaffected

### Requirement: Propagation-free explicit stop via a deny-list
Every provider-token hand-out SHALL refuse a request that matches a broker deny-list entry,
checked before the provider is contacted, independent of OpenFGA read consistency. A deny
entry with no provider SHALL deny all of that agent's grants for that user (an agent-wide
kill), and re-granting consent SHALL clear the matching deny entry.

#### Scenario: Deny-list refuses re-issuance immediately
- **WHEN** a deny-list entry exists for agent X / user U / provider P and X requests a
  token for P
- **THEN** the broker responds 403 before contacting the provider, citing the deny entry

#### Scenario: Agent-wide kill
- **WHEN** a deny entry for agent X / user U has no provider set and X requests a token for
  any of U's grants
- **THEN** every such request is refused

### Requirement: Honest in-flight residual
The system SHALL bound provider-token TTL so the post-revocation in-flight window is small,
and SHALL report that residual window honestly. The system SHALL NOT claim to revoke a
provider access token it cannot revoke (the mock provider has no revocation endpoint); an
already-issued provider token remaining valid until its bounded TTL is disclosed, not hidden.

#### Scenario: Residual is reported, not concealed
- **WHEN** everything is revoked while a provider token issued moments earlier is still within
  its TTL
- **THEN** that token remains usable at the provider until its bounded TTL, and the reported
  time-to-stop discloses this residual rather than claiming instant provider revocation

### Requirement: Measured, surfaced time-to-stop
Each revocation SHALL record a measured time-to-stop — the latency until the agent can no
longer be issued or re-acquire authority — and surface it, together with the in-flight
residual, to the signed-in principal (console) and on the operator dashboard.

#### Scenario: The console reports the kill time
- **WHEN** the principal revokes an agent from the console
- **THEN** the result states the measured new-authority-denied latency and the in-flight
  residual (e.g. "denied in X ms; any already-issued token expires within ≤ N s")

#### Scenario: The dashboard shows time-to-stop
- **WHEN** a revocation completes
- **THEN** a time-to-stop measurement is recorded as a metric and shown on the dashboard,
  joinable to the revoke's trace and audit line

### Requirement: Revocation is a consumable signal (CAEP/SSF)
Each revocation SHALL emit a signed Security Event Token carrying a CAEP `session-revoked`
event (identifying the agent acting for the user, with grant context) to a subscribable
stream, so revocation is consumable by other systems and not only an internal state change.

#### Scenario: A subscriber receives the revocation event
- **WHEN** an agent is revoked and a receiver is subscribed to the signal stream
- **THEN** the receiver obtains a signed SET describing the `session-revoked` event for that
  agent/user, and the same event is present in the audit stream
