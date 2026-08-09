# identity-delegation

## Purpose

User authentication and delegated agent tokens (SPEC.md Flow A; decisions F2-A, F3-A).

## Requirements

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

### Requirement: Headless delegation via Device Authorization Grant
The realm SHALL support OAuth 2.0 Device Authorization Grant (RFC 8628) so a
browserless agent can obtain delegated tokens by displaying a verification URI
and user code and polling the token endpoint, while the user approves in their
own authenticated browser session on a second surface. Agent-side code SHALL
never hold or transmit user credentials to bootstrap delegation; test and demo
code SHALL bootstrap headless agents only through this grant (or the standard
browser flow), with any simulated-human step confined to explicitly-labeled
UI-driving helpers.

#### Scenario: Headless agent delegates without user credentials
- **WHEN** a browserless agent starts the device flow and the user approves the
  code in their own browser session
- **THEN** the agent's poll returns a delegated token (`sub` = user, `azp` =
  agent client) and at no point did any agent-side code possess a user password

#### Scenario: Unapproved device code yields nothing
- **WHEN** the user never approves the device code
- **THEN** the agent's polling terminates in an authorization error at expiry and
  no token is issued

### Requirement: Delegation consent survives a cold start
The explicit delegation consent ("act on your behalf") SHALL be a persisted realm
fixture: the consent-screen scope and the `consentRequired` client setting SHALL
be present in the realm export so the consent moment appears from a clean
`docker compose up` with no live configuration step.

#### Scenario: Consent screen appears from a clean stack
- **WHEN** the stack is brought up from a clean state and a user logs in through
  a consent-required agent client for the first time
- **THEN** Keycloak renders the delegation consent screen before issuing tokens,
  with no out-of-band realm mutation having run
