# revocation — new capability (add-instant-revocation / M9)

## ADDED Requirements

### Requirement: Single-revoke kill fan-out
A single owner-authenticated revoke SHALL fan out, under the same owner invariant, across
every path that can stop an agent: it SHALL delete the `can_use` consent tuple, write a
broker deny-list entry, revoke the agent client's Keycloak sessions and offline/refresh
tokens **for that user**, and emit a revocation signal. The fan-out SHALL be performed by
the broker (the sole writer of authorization state); both existing revoke paths (the M7
consent surface session and the M8 authority console exchanged bearer) SHALL converge on it.

#### Scenario: One revoke stops the agent on every path
- **WHEN** the owner revokes agent X for provider P
- **THEN** the `can_use` tuple is deleted, a deny-list entry exists for X, X's Keycloak
  offline sessions for that user are revoked, and a revocation signal is emitted — from the
  one revoke action

#### Scenario: Revocation is scoped to the agent, not the human
- **WHEN** the kill fan-out revokes the agent client's sessions/offline tokens
- **THEN** only the agent client's sessions for that user are revoked; the human's own
  browser/SSO sessions are unaffected

### Requirement: The agent cannot re-acquire authority after revoke
After revoke, the agent SHALL NOT be able to obtain a new user-bound token for that user —
neither by refreshing an offline/refresh token nor by re-exchanging — so a stopped agent
cannot re-acquire the authority it lost.

#### Scenario: Offline token cannot re-mint
- **WHEN** a revoked agent presents its offline/refresh token to mint a fresh user-bound
  token for that user and re-exchange to `aud=token-broker`
- **THEN** the attempt is refused; no fresh user-bound token is issued for that user

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
