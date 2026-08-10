# token-brokering — delta (add-instant-revocation / M9)

## MODIFIED Requirements

### Requirement: Token hand-out validation chain
On `POST /v1/tokens/{provider}` the broker SHALL validate, in order: (1) the bearer token's signature against Keycloak JWKS, (2) `aud = token-broker`, (3) requested scopes are a subset of the grant's granted scopes, (4) an OpenFGA check that `agent:{azp}` has `can_use` on `grant:{user}/{provider}`, and (5) no matching broker deny-list entry exists for `agent:{azp}` / `user` (with a null-provider entry denying all of that agent's grants for the user). Only when all pass SHALL a provider access token be returned. The deny-list check is a propagation-free "stop now" evaluated on every hand-out, independent of OpenFGA read consistency.

#### Scenario: Valid request yields access token only
- **WHEN** an agent with a valid broker-audience token and a `can_use` tuple requests scopes within the grant
- **THEN** the response contains a provider access token and expiry, and never a refresh token

#### Scenario: Over-broad scope refused
- **WHEN** the requested scopes exceed the grant's granted scopes
- **THEN** the broker responds 403 without contacting the provider

#### Scenario: Missing consent tuple refused
- **WHEN** the requesting agent has no `can_use` tuple for the grant
- **THEN** the broker responds 403 and logs the denial

#### Scenario: Deny-listed agent refused before the provider
- **WHEN** a deny-list entry matches the requesting agent (for this grant, or an agent-wide entry with no provider)
- **THEN** the broker responds 403 before contacting the provider, even if a stale `can_use` tuple were still present

### Requirement: Re-issuance interval and TTL honesty
The broker SHALL cap its hand-out interval so returned `expires_in` is small enough that the post-revocation in-flight window is bounded and legible (demo default 120 seconds; configurable). Residual validity of the underlying provider token beyond the hand-out interval is provider-controlled and MUST be documented per provider in the threat model's TTL table (Google ~1h; GitHub App ~8h). The broker SHALL NOT claim a provider token expires at the hand-out interval, and SHALL report the in-flight residual honestly on revocation.

#### Scenario: Hand-out interval enforced
- **WHEN** the broker returns any provider token
- **THEN** `expires_in` is at most the configured hand-out cap (demo default 120)

#### Scenario: TTL table exists
- **WHEN** the threat model is reviewed
- **THEN** it contains a per-provider table of actual token lifetimes and residual-exposure notes

#### Scenario: Residual disclosed on revocation
- **WHEN** an agent is revoked while a provider token it holds is still within its hand-out TTL
- **THEN** the reported time-to-stop discloses the remaining in-flight residual rather than claiming instant provider revocation
