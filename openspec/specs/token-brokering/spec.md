# token-brokering

## Purpose

Provider-token lifecycle: leases, hand-out, capability manifest, audit (SPEC.md Flow B; decisions F3-A, F4-A+C).

## Requirements

### Requirement: Token hand-out validation chain
On `POST /v1/tokens/{provider}` the broker SHALL validate, in order: (1) the bearer token's signature against Keycloak JWKS, (2) `aud = token-broker`, (3) requested scopes are a subset of the grant's granted scopes, (4) an OpenFGA check that `agent:{azp}` has `can_use` on `grant:{user}/{provider}`. Only when all pass SHALL a provider access token be returned.

#### Scenario: Valid request yields access token only
- **WHEN** an agent with a valid broker-audience token and a `can_use` tuple requests scopes within the grant
- **THEN** the response contains a provider access token and expiry, and never a refresh token

#### Scenario: Over-broad scope refused
- **WHEN** the requested scopes exceed the grant's granted scopes
- **THEN** the broker responds 403 without contacting the provider

#### Scenario: Missing consent tuple refused
- **WHEN** the requesting agent has no `can_use` tuple for the grant
- **THEN** the broker responds 403 and logs the denial

### Requirement: Refresh credentials never leave OpenBao
Long-lived provider credentials SHALL exist only inside OpenBao, held in broker memory only transiently during a refresh operation. No API response, log line, or audit record SHALL contain a refresh credential.

#### Scenario: Credential absent from all outputs
- **WHEN** any broker endpoint is exercised, including error paths
- **THEN** no response body or log output contains the stored refresh credential

### Requirement: Re-issuance interval and TTL honesty
The broker SHALL cap its hand-out interval at 15 minutes: returned `expires_in` is at most 900 seconds. Residual validity of the underlying provider token beyond the hand-out interval is provider-controlled and MUST be documented per provider in the threat model's TTL table (Google ~1h; GitHub App ~8h). The broker SHALL NOT claim provider tokens expire at 15 minutes.

#### Scenario: Hand-out interval enforced
- **WHEN** the broker returns any provider token
- **THEN** `expires_in` is at most 900

#### Scenario: TTL table exists
- **WHEN** the threat model is reviewed
- **THEN** it contains a per-provider table of actual token lifetimes and residual-exposure notes

### Requirement: Provider capability manifest
Each provider integration SHALL declare `supports_refresh` and `supports_scope_narrowing` in a provider manifest. Enforcement is per-capability: cryptographic narrowing where the provider supports it; policy refusal (reject over-broad requests, never silently widen or fake-narrow) where it does not. The GitHub integration SHALL use a GitHub App with user-token expiration enabled (`supports_refresh: true`).

#### Scenario: Refresh loop on a refresh-capable provider
- **WHEN** the stored GitHub App user token has expired and an agent requests a token
- **THEN** the broker refreshes via the provider using the stored refresh token and returns a fresh access token

#### Scenario: Non-narrowing provider refuses rather than pretends
- **WHEN** a scope-narrowing request arrives for a provider with `supports_scope_narrowing: false` and the request is within granted scopes
- **THEN** the broker returns the token with its actual scopes and the response accurately reports them (no claimed narrowing)

### Requirement: Issuance audit log
Every token issuance and every denial SHALL be audit-logged with `{user, agent (azp), provider, scopes, ttl}` and a correlation ID linking related broker, Keycloak, and approval events. In addition to the persisted record, every audit event SHALL be emitted to the telemetry pipeline in realtime as it occurs, carrying the same correlation ID as the persisted record, so the audit trail is watchable live (Loki-queryable) and joinable to the flow's distributed trace.

#### Scenario: Audit on issuance
- **WHEN** a provider token is issued
- **THEN** an audit record exists containing user, agent, provider, scopes, ttl, and a correlation ID

#### Scenario: Audit event emitted in realtime
- **WHEN** a token issuance or denial occurs
- **THEN** an audit event with the same correlation ID as the persisted record is queryable in the log backend within seconds, without waiting for any batch export
