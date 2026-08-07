# grant-acquisition

## Purpose

Third-party grant acquisition via Keycloak identity brokering (SPEC.md Flow B step 1 as redesigned; decisions Q2-B, F9).

## Requirements

### Requirement: Grants acquired via Keycloak account linking
Third-party provider grants (Google, GitHub) SHALL be acquired exclusively through Keycloak identity providers with Store Tokens enabled, connected to an existing account via client-initiated account linking (application-initiated action `kc_action=idp_link:<alias>`). The Token Broker SHALL NOT implement its own provider Authorization Code flows, authorize endpoints, or consent surfaces.

#### Scenario: Linking a provider seeds the grant
- **WHEN** an authenticated user completes the `idp_link` flow for GitHub
- **THEN** Keycloak stores the provider tokens for that user under the same Keycloak identity, with no separate broker-side consent ceremony

#### Scenario: Linking requires an authenticated session
- **WHEN** an unauthenticated request attempts to initiate account linking
- **THEN** Keycloak requires login before the provider consent screen is reached

### Requirement: Broker imports the refresh credential into OpenBao
After linking, the Token Broker SHALL retrieve the stored provider token from Keycloak's broker endpoint and import the long-lived credential (refresh token, or the provider token itself where no refresh token exists) into OpenBao at `secret/grants/{user_id}/{provider}`, recording granted scopes in its own database. From that point the broker owns the grant lifecycle.

#### Scenario: Import after linking
- **WHEN** the broker completes grant import for a newly linked provider
- **THEN** the credential exists in OpenBao at the grant path, the grant row records provider and granted scopes, and no API response has contained the credential

### Requirement: Grant revocation
The system SHALL support user-initiated grant revocation that revokes the credential at the provider (where the provider supports revocation), deletes it from OpenBao, removes the grant record, and deletes all `can_use` tuples referencing the grant.

#### Scenario: Revoked grant is unusable
- **WHEN** a user revokes their GitHub grant and an agent subsequently requests a GitHub token
- **THEN** the broker returns an error and no provider token is issued

### Requirement: Static per-provider scope configuration is documented
Provider scopes SHALL be configured statically per identity provider in the Keycloak realm. The documentation MUST state this trade-off explicitly (no incremental per-request scope escalation; matches the commercial reference product).

#### Scenario: Scope change requires re-linking
- **WHEN** the realm's GitHub IdP scope configuration changes
- **THEN** existing grants retain their originally granted scopes until the user re-links, and the documentation describes this behavior
