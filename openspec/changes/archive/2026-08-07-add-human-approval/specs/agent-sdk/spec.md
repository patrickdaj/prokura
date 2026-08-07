## ADDED Requirements

### Requirement: Human-approval helper

The SDK SHALL provide `require_approval(action, params, *, scopes)` that gates a
sensitive action on human approval via CIBA. It SHALL register the structured
`{action, params}` payload with the approval service, obtain a reference ID,
initiate the CIBA request with that reference ID as the binding message, poll to
completion, and return an action token that carries the reference ID. The helper
SHALL NOT put agent-authored prose into the binding message, and SHALL treat the
returned token as an in-memory, short-lived value (never persisted or logged).

#### Scenario: Approval granted yields an action token

- **WHEN** an agent calls `require_approval("email.send", {...})` and the user
  approves in the trusted UI
- **THEN** the helper returns an action token whose reference ID matches the
  registered payload, usable exactly once at the gated tool

#### Scenario: Denial raises a distinct error

- **WHEN** the user denies the pending action
- **THEN** the helper raises a distinct, catchable approval-denied error and
  returns no token

#### Scenario: Timeout raises a distinct error

- **WHEN** the CIBA request expires with no decision (120 s)
- **THEN** the helper raises a distinct, catchable approval-timeout error and
  returns no token

#### Scenario: The helper never persists the token

- **WHEN** any `require_approval()` call runs, including the denial and timeout
  paths
- **THEN** no action token or CIBA credential appears in log output or on the
  filesystem
