# per-agent-consent

## Purpose

Per-agent grant authorization via OpenFGA (decisions F1-A, Q3-B). This is a security gate, not a convenience: with dynamic client registration enabled for MCP, any client can register itself — the consent tuple is what stands between a registered client and the user's grants.

## Requirements

### Requirement: Valid direct-assignment FGA model
The OpenFGA authorization model SHALL define grant usage as a direct assignment (`define can_use: [agent]`) with no self-referential or cross-object-join constructs. The model MUST load successfully in OpenFGA. (Replaces the invalid `[agent] and operator from can_use` construct — F1.)

#### Scenario: Model loads
- **WHEN** `model.fga` is written to the OpenFGA store at stack startup
- **THEN** OpenFGA accepts the model and check queries against it succeed

### Requirement: Consent screen writes the tuple
An agent SHALL gain access to a grant only after the user approves it on a
per-agent consent screen ("Allow <agent> to use your <provider> grant —
[scopes]"), rendered in an authenticated Keycloak browser session established
via OIDC Authorization Code + PKCE login on the broker itself. No consent
surface SHALL accept a bearer token carried in a URL. Approval writes the
`agent:{id} can_use grant:{user}/{provider}` tuple with the grant owner taken
from the session's subject; nothing else creates consent.

#### Scenario: Approval grants exactly one agent
- **WHEN** the user approves agent `summarizer` for their GitHub grant
- **THEN** `summarizer` passes the broker's FGA check for that grant and every other agent still fails it

#### Scenario: No implicit consent
- **WHEN** a grant is created and no consent has been given to any agent
- **THEN** no agent passes the FGA check for that grant

#### Scenario: Consent requires a real session
- **WHEN** the consent screen is opened with no active session (with or without a
  `?token=` query parameter)
- **THEN** the user is redirected through Keycloak login before any consent target
  is rendered, and any URL-carried token is ignored

#### Scenario: Session subject is the tuple's owner
- **WHEN** a consent approval is posted from an authenticated session
- **THEN** the written tuple's grant owner is the session's subject — a session
  belonging to user A cannot create consent on a grant owned by user B

### Requirement: Broker is the sole tuple writer with a write-time invariant
Only the Token Broker SHALL write `can_use` tuples, and it MUST refuse any write where the agent's `operator` is not the grant's `owner`. This moves the operator==owner property from the FGA model into broker code; the threat model MUST document the broker as a trusted tuple writer.

#### Scenario: Cross-user write refused
- **WHEN** a tuple write is attempted authorizing an agent operated by user A on a grant owned by user B
- **THEN** the broker refuses the write and logs it

### Requirement: Consent revocation
The user SHALL be able to revoke a single agent's access to a grant without revoking the grant itself, from either of two owner-authenticated paths: the broker's own consent surface session (M7 path), or the authority console — which relays the owner's authority as an exchanged user-bound bearer token (`aud=token-broker`) whose verified subject the broker takes as the owner. Both paths SHALL converge on the same broker revocation code and emit the same audit event with the acting user. Revocation SHALL take effect within seconds rather than only on the next hand-out: the same revoke fans out to delete the `can_use` tuple, write a broker deny-list entry, and emit a revocation signal (the M9 kill switch). It SHALL be scoped — the agent's other consented grants and its Keycloak session are untouched. Re-acquiring the revoked grant SHALL be blocked even with a fresh user-bound token (the deny-list denies it), and any provider token already issued remains valid only until its bounded TTL, which SHALL be reported honestly.

#### Scenario: Revoked agent loses access
- **WHEN** the user revokes agent `summarizer`'s consent for their GitHub grant and `summarizer` then requests a token
- **THEN** the broker responds 403 while other consented agents remain unaffected

#### Scenario: Console revocation equals surface revocation
- **WHEN** the owner revokes an agent from the authority console
- **THEN** the same tuple delete, deny-list entry, revocation signal, and audit event occur as when revoking from the broker's consent surface, and the owner is the bearer's verified subject

#### Scenario: A foreign subject cannot revoke
- **WHEN** a bearer whose subject is user B presents a revocation for a grant
  owned by user A
- **THEN** no tuple belonging to A is deleted

#### Scenario: Revoked grant cannot be re-acquired
- **WHEN** a revoked agent obtains a fresh user-bound token and requests the revoked grant again
- **THEN** the broker refuses (the deny-list denies before the provider is contacted), so a fresh token is no re-acquisition path — re-consent is required
