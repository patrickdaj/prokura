## ADDED Requirements

### Requirement: Mock provider realm is the default grant source; real providers are a documented extension

The default, offline grant source SHALL be a mock external provider implemented
as a separate Keycloak realm (`acme`) connected to the `prokura` realm as an OIDC
identity provider with Store Tokens enabled. This lets the entire
link → import → broker flow run with zero external credentials and no outbound
network, while exercising the *real* Keycloak identity-brokering and stored-token
machinery (§1 of the design). Connecting a real provider (GitHub App, Google)
SHALL be a documented bring-your-own-credentials extension — adding an identity
provider block with real client id/secret and scopes — and SHALL NOT be required
to run the reference stack. The mock realm SHALL NOT be presented as a real
provider; documentation MUST state that `acme` is a stand-in.

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
