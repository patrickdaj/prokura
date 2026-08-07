# agent-sdk

## Purpose

The Python client library (`prokura-py`) agents use to obtain and use delegated identity. M1 scope: `exchange()` only. Later milestones add `get_provider_token()` (M2), `require_approval()` (M3), `fga_filter()` (M5). Decision Q5: Python v0, TypeScript v1.

## Requirements

### Requirement: Delegated token exchange helper
The SDK SHALL provide `exchange(subject_token, audience, scopes)` that performs an RFC 8693 token exchange against Keycloak and returns the resulting access token. The returned token SHALL carry the original user as `sub`, the agent client as `azp`, only the requested scopes, and the requested `audience` in `aud`.

#### Scenario: Exchange to the tools audience
- **WHEN** an agent calls `exchange(user_token, audience="agent-tools-api", scopes=["tools:read"])`
- **THEN** it receives a token with `sub`=user, `azp`=agent client, `aud` containing `agent-tools-api`, and no scopes beyond `tools:read`

#### Scenario: Exchange to the broker audience
- **WHEN** an agent calls `exchange(user_token, audience="token-broker", ...)`
- **THEN** the returned token's `aud` contains `token-broker` (satisfying the broker's F2-A audience check)

### Requirement: Audience denial surfaces as a clear error
When Keycloak refuses an exchange because the client lacks permission for the requested audience, the SDK SHALL raise a distinct, catchable error (not a generic HTTP failure) naming the denied audience.

#### Scenario: Un-permitted audience
- **WHEN** an agent requests exchange to an audience its client is not permitted for
- **THEN** the SDK raises a `ExchangeDenied` (or equivalently named) error identifying the audience, and no token is returned

### Requirement: The SDK never persists tokens
The SDK SHALL treat tokens as in-memory, short-lived values: it MUST NOT write access or subject tokens to disk, logs, or any cache that outlives the process.

#### Scenario: No token on disk or in logs
- **WHEN** any SDK operation runs, including error paths
- **THEN** no access or subject token value appears in log output or on the filesystem
