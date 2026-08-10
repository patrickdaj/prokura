# grant-acquisition — delta (add-authority-console / M8)

## MODIFIED Requirements

### Requirement: Grants acquired via Keycloak account linking
Third-party provider grants (Google, GitHub) SHALL be acquired exclusively through Keycloak identity providers with Store Tokens enabled, connected to an existing account via client-initiated account linking (application-initiated action `kc_action=idp_link:<alias>`). The Token Broker SHALL NOT implement its own provider Authorization Code flows, authorize endpoints, or consent surfaces. A real person SHALL be able to reach the linking flow from a user-facing surface (the authority console) in their own authenticated session, and the resulting grant SHALL be imported through the broker's existing import endpoint with no admin API or demo-driver step.

#### Scenario: Linking a provider seeds the grant
- **WHEN** an authenticated user completes the `idp_link` flow for GitHub
- **THEN** Keycloak stores the provider tokens for that user under the same Keycloak identity, with no separate broker-side consent ceremony

#### Scenario: Linking requires an authenticated session
- **WHEN** an unauthenticated request attempts to initiate account linking
- **THEN** Keycloak requires login before the provider consent screen is reached

#### Scenario: A real person links from the console end-to-end
- **WHEN** a signed-in principal clicks "connect a provider" in the authority
  console, completes the provider login in their browser, and returns
- **THEN** the console imports the grant with the principal's own exchanged token
  and the grant appears in their register — no admin API or demo driver ran
