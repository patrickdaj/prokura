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

### Requirement: Mock provider realm is the default grant source; real providers are a documented extension

The default, offline grant source SHALL be a mock external provider implemented
as a separate Keycloak realm (`acme`) connected to the `prokura` realm as an OIDC
identity provider with Store Tokens enabled. This lets the entire
link → import → broker flow run with zero external credentials and no outbound
network, while exercising the *real* Keycloak identity-brokering and stored-token
machinery. Connecting a real provider (GitHub App, Google) SHALL be a documented
bring-your-own-credentials extension — adding an identity provider block with
real client id/secret and scopes — and SHALL NOT be required to run the reference
stack. The mock realm SHALL NOT be presented as a real provider; documentation
MUST state that `acme` is a stand-in.

#### Scenario: Linking the mock provider seeds a grant offline

- **WHEN** an authenticated `prokura` user completes `kc_action=idp_link:acme`
  with the stack running and no outbound network access
- **THEN** Keycloak stores the `acme` provider tokens under that user's identity
  and the broker can import the credential into OpenBao, with no call to any
  external provider

#### Scenario: Real providers documented as a credential swap, not a rewrite

- **WHEN** an operator wants to connect a real GitHub App or Google account
- **THEN** the documentation describes adding an identity provider block with
  real credentials and scopes as the only required change, and the broker,
  consent, and hand-out code paths are unchanged

#### Scenario: Mock provider is labelled as a stand-in

- **WHEN** the `acme` realm or its grants are surfaced in the demo, docs, or
  threat model
- **THEN** they are described as a mock external provider standing in for
  GitHub/Google, never as a production provider integration
