# per-agent-consent — delta (add-instant-revocation / M9)

## MODIFIED Requirements

### Requirement: Consent revocation
The user SHALL be able to revoke a single agent's access to a grant without revoking the grant itself, from either of two owner-authenticated paths: the broker's own consent surface session (M7 path), or the authority console — which relays the owner's authority as an exchanged user-bound bearer token (`aud=token-broker`) whose verified subject the broker takes as the owner. Both paths SHALL converge on the same broker revocation code and emit the same audit event with the acting user. Revocation SHALL take effect within seconds rather than only on the next hand-out: the same revoke fans out to delete the `can_use` tuple, write a broker deny-list entry, and emit a revocation signal (the M9 kill switch). It SHALL be scoped — the agent's other consented grants and its Keycloak session are untouched. Re-acquiring the revoked grant SHALL be blocked even with a fresh user-bound token (the deny-list denies it), and any provider token already issued remains valid only until its bounded TTL, which SHALL be reported honestly.

#### Scenario: Revoked agent loses access
- **WHEN** the user revokes agent `summarizer`'s consent for their GitHub grant and `summarizer` then requests a token
- **THEN** the broker responds 403 while other consented agents remain unaffected

#### Scenario: Console revocation equals surface revocation
- **WHEN** the owner revokes an agent from the authority console
- **THEN** the same tuple delete, deny-list entry, revocation signal, and audit event occur as when revoking from the broker's consent surface, and the owner is the bearer's verified subject

#### Scenario: A foreign subject cannot revoke
- **WHEN** a bearer whose subject is user B presents a revocation for a grant owned by user A
- **THEN** no tuple belonging to A is deleted

#### Scenario: Revoked grant cannot be re-acquired
- **WHEN** a revoked agent obtains a fresh user-bound token and requests the revoked grant again
- **THEN** the broker refuses (the deny-list denies before the provider is contacted), so a fresh token is no re-acquisition path — re-consent is required
