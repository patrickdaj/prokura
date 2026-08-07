# identity-delegation

User authentication and delegated agent tokens (SPEC.md Flow A; decisions F2-A, F3-A).

## ADDED Requirements

### Requirement: User authentication via OIDC
The system SHALL authenticate users through Keycloak using OIDC Authorization Code flow with PKCE. Agent applications SHALL never handle user credentials directly.

#### Scenario: Successful login
- **WHEN** a user completes the Keycloak login flow from an agent application
- **THEN** the application holds a user access token with `sub` = the user, issued by the Prokura realm

### Requirement: Delegated agent token via RFC 8693 token exchange
The system SHALL issue delegated agent tokens only through RFC 8693 token exchange: the agent application presents the user's `subject_token` and receives a token with `sub` = user, `azp` = agent client, containing only the requested (reduced) scopes. Every downstream action MUST be attributable to user-via-agent through this claim pair.

#### Scenario: Exchange preserves subject and marks the agent
- **WHEN** an agent client exchanges a user token requesting `scope=tools:read tools:execute`
- **THEN** the returned token contains the original user `sub`, the agent client as `azp`, and no scopes beyond those requested

#### Scenario: Exchange denied without explicit permission
- **WHEN** an agent client requests exchange toward an audience it has not been explicitly permitted for in Keycloak
- **THEN** the token endpoint refuses the exchange (no wildcard exchange permissions exist in the realm)

### Requirement: Broker calls require a broker-audience token
Agents calling the Token Broker SHALL first exchange for a token with `audience = token-broker`. The broker MUST reject any token whose `aud` claim is not the broker itself (confused-deputy defense, F2-A).

#### Scenario: Correctly addressed token accepted
- **WHEN** an agent presents a token with `aud = token-broker` to the broker
- **THEN** the broker proceeds to its remaining authorization checks

#### Scenario: Wrong-audience token rejected
- **WHEN** an agent presents a token with `aud = agent-tools-api` (or any non-broker audience) to the broker
- **THEN** the broker rejects the request without evaluating scopes or FGA tuples

### Requirement: Keycloak-issued token lifetime bound
All Keycloak-issued tokens held by agents SHALL have a TTL of at most 15 minutes. (Provider-issued token lifetimes are governed by `token-brokering`, not this bound — F3-A.)

#### Scenario: Exchanged token expiry
- **WHEN** any token is issued to an agent client by Keycloak
- **THEN** its `exp` is at most 15 minutes after issuance
