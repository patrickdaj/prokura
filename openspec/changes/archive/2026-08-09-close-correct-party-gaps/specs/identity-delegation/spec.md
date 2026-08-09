# identity-delegation — delta (close-correct-party-gaps / M7)

## ADDED Requirements

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
