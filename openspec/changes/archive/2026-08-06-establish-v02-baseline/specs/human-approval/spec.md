# human-approval

CIBA-gated sensitive actions with structured, replay-proof approval (SPEC.md Flow C; decisions F5-A, F6-A, F7-A+B, F8-A).

## ADDED Requirements

### Requirement: Structured approval payload, reference-ID binding message
Before initiating CIBA for a sensitive action, the agent SHALL register a structured action payload (`{action, params}`) with the approval service and receive a reference ID. The CIBA `binding_message` SHALL carry only that reference ID and MUST conform to Keycloak's validation (`^[a-zA-Z0-9-._+/!?#]{1,50}$`). Free-text agent-authored approval prose is prohibited everywhere in the flow.

#### Scenario: Registration then CIBA
- **WHEN** an agent needs approval for `email.send` with recipient and subject parameters
- **THEN** the payload is registered with the approval service, and the backchannel request's `binding_message` contains only the returned reference ID and passes Keycloak validation

### Requirement: Trusted rendering
The approval UI SHALL fetch the action payload from the approval service by reference ID and render it itself. Agent-authored text SHALL never be rendered to the approving human. The approval service records a hash of the payload at registration time.

#### Scenario: UI renders service-held payload
- **WHEN** the user opens a pending approval
- **THEN** the rendered action, parameters, requesting agent, and scopes come from the approval service's stored payload, not from any agent-supplied string

### Requirement: Decisions only via authenticated UI; notifications carry no capability
Approval and denial SHALL occur exclusively in the approval UI behind an authenticated Keycloak session; the approval service (not the user's device) relays the decision to Keycloak's CIBA callback. Notifications (self-hosted ntfy with ACLs, per-user unguessable topics) SHALL contain at most a deep link and reference ID — no action details and no approval capability.

#### Scenario: Spoofed notification is inert
- **WHEN** an attacker publishes a fabricated message to a notification topic
- **THEN** no approval state changes, and the genuine pending action can still only be decided in the authenticated UI

#### Scenario: Notification leaks nothing sensitive
- **WHEN** any approval notification is published
- **THEN** it contains no action parameters — only a deep link and reference ID

### Requirement: Hash-verified execution and single-use enforcement
The action token issued on approval SHALL carry the approval reference ID (scope or claim). Before executing, the resource server MUST verify the action it is about to perform matches the approved payload hash, and MUST reject any reference ID it has already consumed. This makes the "single-use action token" acceptance criterion testable (F8-A).

#### Scenario: Parameter mismatch refused
- **WHEN** an agent presents an approved action token but attempts the action with parameters differing from the approved payload
- **THEN** the resource server refuses execution

#### Scenario: Replay refused
- **WHEN** an agent presents the same approved action token after the action has executed once
- **THEN** the resource server refuses re-execution

### Requirement: Denial and timeout abort cleanly
On user denial or on backchannel timeout (120 s), the agent SHALL receive an error from the token endpoint, no action token SHALL be issued, and the pending action SHALL be marked terminal in the approval service.

#### Scenario: Denial
- **WHEN** the user denies a pending action
- **THEN** the agent's CIBA poll returns an error and the action never executes

#### Scenario: Timeout
- **WHEN** 120 seconds elapse with no decision
- **THEN** the request expires, the agent aborts cleanly, and the approval UI shows the action as expired

### Requirement: CIBA transport via built-in HTTP channel
The Keycloak↔approval-service transport SHALL use Keycloak's built-in CIBA HTTP authentication channel (delegation request POSTed to the approval service; decision returned on Keycloak's CIBA callback endpoint authorized by the delegation bearer token). A custom Java SPI is permitted only as a documented fallback if the M0 spike proves the built-in channel unusable.

#### Scenario: Round trip without custom SPI
- **WHEN** a CIBA request is initiated in the deployed stack
- **THEN** the approval service receives Keycloak's delegation POST (including the binding message) and its decision callback completes authentication, with no custom Keycloak extension installed
