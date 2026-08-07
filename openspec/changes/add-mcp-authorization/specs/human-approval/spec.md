## MODIFIED Requirements

### Requirement: Structured approval payload, reference-ID binding message

The approval **trigger** SHALL live on the resource server, not the agent. When
an agent attempts a sensitive action without an approved action token, the
resource server SHALL refuse with an `approval_required` challenge and SHALL
itself register the structured action payload (`{action, params}`) it actually
received with the approval service, obtaining a reference ID and recording the
payload hash. The agent then runs the (client-initiated) CIBA flow with that
reference ID as the binding message and retries the action. The CIBA
`binding_message` SHALL carry only that reference ID and MUST conform to
Keycloak's validation (`^[a-zA-Z0-9-._+/!?#]{1,50}$`). Free-text agent-authored
approval prose is prohibited everywhere in the flow, and the action that is
approved SHALL be the one the resource server observed, not one the agent
described.

#### Scenario: Reactive challenge registers the real action

- **WHEN** an agent calls a sensitive tool (e.g. `email.send`) without an approved
  action token
- **THEN** the resource server responds with an `approval_required` challenge,
  registers the exact `{action, params}` it received (recording its hash), and
  returns the reference ID for the agent to drive CIBA — the agent does not author
  the payload

#### Scenario: Retry after approval executes the observed action

- **WHEN** the human approves and the agent retries the tool call with the action
  token
- **THEN** the resource server verifies the action it is about to perform matches
  the registered hash and executes it exactly once
