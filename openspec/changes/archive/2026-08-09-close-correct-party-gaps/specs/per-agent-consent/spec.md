# per-agent-consent — delta (close-correct-party-gaps / M7)

## MODIFIED Requirements

### Requirement: Consent screen writes the tuple
An agent SHALL gain access to a grant only after the user approves it on a
per-agent consent screen ("Allow <agent> to use your <provider> grant —
[scopes]"), rendered in an authenticated Keycloak browser session established
via OIDC Authorization Code + PKCE login on the broker itself. No consent
surface SHALL accept a bearer token carried in a URL. Approval writes the
`agent:{id} can_use grant:{user}/{provider}` tuple with the grant owner taken
from the session's subject; nothing else creates consent.

#### Scenario: Approval grants exactly one agent
- **WHEN** the user approves agent `summarizer` for their GitHub grant
- **THEN** `summarizer` passes the broker's FGA check for that grant and every other agent still fails it

#### Scenario: No implicit consent
- **WHEN** a grant is created and no consent has been given to any agent
- **THEN** no agent passes the FGA check for that grant

#### Scenario: Consent requires a real session
- **WHEN** the consent screen is opened with no active session (with or without a
  `?token=` query parameter)
- **THEN** the user is redirected through Keycloak login before any consent target
  is rendered, and any URL-carried token is ignored

#### Scenario: Session subject is the tuple's owner
- **WHEN** a consent approval is posted from an authenticated session
- **THEN** the written tuple's grant owner is the session's subject — a session
  belonging to user A cannot create consent on a grant owned by user B
