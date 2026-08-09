# human-approval

## Purpose

CIBA-gated sensitive actions with structured, replay-proof approval (SPEC.md Flow C; decisions F5-A, F6-A, F7-A+B, F8-A).

## Requirements

### Requirement: Structured approval payload, reference-ID binding message
The approval **trigger** SHALL live on the resource server, not the agent. When
an agent attempts a sensitive action without an approved action token, the
resource server SHALL refuse with an `approval_required` challenge and SHALL
itself register the structured action payload (`{action, params}`) it actually
received with the approval service, obtaining a reference ID and recording the
payload hash. Registration itself triggers the server-initiated CIBA ceremony;
the agent then waits and retries the action with the action token — the agent
performs no CIBA step. The CIBA `binding_message` SHALL carry only the reference
ID and MUST conform to Keycloak's validation (`^[a-zA-Z0-9-._+/!?#]{1,50}$`).
Free-text agent-authored approval prose is prohibited everywhere in the flow,
and the action that is approved SHALL be the one the resource server observed,
not one the agent described.

#### Scenario: Reactive challenge registers the real action
- **WHEN** an agent calls a sensitive tool (e.g. `email.send`) without an approved
  action token
- **THEN** the resource server responds with an `approval_required` challenge,
  registers the exact `{action, params}` it received (recording its hash), and
  the registration triggers the CIBA ceremony server-side — the agent does not
  author the payload and does not drive the ceremony

#### Scenario: Retry after approval executes the observed action
- **WHEN** the human approves and the agent retries the tool call with the action
  token
- **THEN** the resource server verifies the action it is about to perform matches
  the registered hash and executes it exactly once

### Requirement: Trusted rendering
The approval UI SHALL fetch the action payload from the approval service by reference ID and render it itself. Agent-authored text SHALL never be rendered to the approving human. The approval service records a hash of the payload at registration time.

#### Scenario: UI renders service-held payload
- **WHEN** the user opens a pending approval
- **THEN** the rendered action, parameters, requesting agent, and scopes come from the approval service's stored payload, not from any agent-supplied string

### Requirement: Decisions only via authenticated UI; notifications carry no capability
Approval and denial SHALL occur exclusively in the approval UI behind an
authenticated Keycloak browser session established via OIDC Authorization Code +
PKCE login on the approval service itself. No decision surface SHALL accept a
bearer token carried in a URL. A decision SHALL be accepted only when the
session's subject is the user the pending approval targets. The approval service
(not the user's device) relays the decision to Keycloak's CIBA callback.
Notifications (self-hosted ntfy with ACLs, per-user unguessable topics) SHALL
contain at most a deep link and reference ID — no action details and no approval
capability — and the deep link SHALL be followable by a human: opening it without
a session redirects through login and returns to the referenced approval.

#### Scenario: Deep link is followable end-to-end
- **WHEN** the user opens the notification deep link with no active session
- **THEN** they are redirected through Keycloak login and land on the rendered
  pending approval, with the reference preserved across the login round-trip

#### Scenario: URL-carried credentials rejected
- **WHEN** a request presents a bearer token via query parameter to any approval
  surface or decision endpoint
- **THEN** the token is ignored and the request is treated as unauthenticated

#### Scenario: Wrong user cannot decide
- **WHEN** an authenticated session whose subject is not the approval's target
  user posts a decision
- **THEN** the decision is refused and the approval remains pending

#### Scenario: Spoofed notification is inert
- **WHEN** an attacker publishes a fabricated message to a notification topic
- **THEN** no approval state changes, and the genuine pending action can still
  only be decided in the authenticated UI

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
On user denial or on backchannel timeout, the approval SHALL be marked terminal
in the approval service, no action token SHALL be redeemable, and the agent's
retry with the action token SHALL be refused with a terminal error
distinguishing denial/expiry from a pending state. The approval service (as
ceremony owner) SHALL observe the denial/timeout on its own poll; no agent-side
token-endpoint interaction exists.

#### Scenario: Denial
- **WHEN** the user denies a pending action and the agent retries with the action
  token
- **THEN** the retry is refused with a terminal denial error and the action never
  executes

#### Scenario: Timeout
- **WHEN** the backchannel window elapses with no decision
- **THEN** the request expires, the agent's retry is refused as expired, and the
  approval UI shows the action as expired

### Requirement: CIBA transport via built-in HTTP channel
The Keycloak↔approval-service transport SHALL use Keycloak's built-in CIBA HTTP authentication channel (delegation request POSTed to the approval service; decision returned on Keycloak's CIBA callback endpoint authorized by the delegation bearer token). A custom Java SPI is permitted only as a documented fallback if the M0 spike proves the built-in channel unusable.

#### Scenario: Round trip without custom SPI
- **WHEN** a CIBA request is initiated in the deployed stack
- **THEN** the approval service receives Keycloak's delegation POST (including the binding message) and its decision callback completes authentication, with no custom Keycloak extension installed

### Requirement: Server-initiated CIBA ceremony
The approval service SHALL initiate the CIBA ceremony itself at registration time:
on registering an action, it SHALL call Keycloak's backchannel authentication
endpoint using its own confidential client, with `login_hint` set to the user it
verified from the registration and `binding_message` set to the new reference ID.
It SHALL store the `auth_req_id`, complete the ceremony (poll after a decision),
and discard the CIBA-issued token — the ceremony, not the token, is the product.
No agent-facing client SHALL hold the CIBA grant; the agent's entire role in the
approval flow is: receive the `approval_required` challenge, wait, retry with the
action token.

#### Scenario: Registration triggers the ceremony without the agent
- **WHEN** the resource server registers a refused sensitive action
- **THEN** the approval service initiates CIBA for the registered user with the
  reference ID as binding message, and the delegation reaches the approval
  service's CIBA channel receiver with no agent-side call to any Keycloak
  endpoint

#### Scenario: Agent cannot initiate the ceremony
- **WHEN** any agent-facing client attempts the CIBA grant at the token endpoint
- **THEN** Keycloak refuses the grant for that client

### Requirement: CIBA channel receiver is authenticated and bounded
The approval service's CIBA delegation receiver SHALL authenticate Keycloak's
delegation POST by verifying the delegation bearer as a realm-signed JWT whose
authorized party is the approval service's own CIBA client (the built-in HTTP
channel already sends one — spike finding S4; a shared-secret header is not
configurable on the SPI and not needed), and SHALL bound the request body size,
rejecting unauthenticated or oversized requests before parsing. (Closes SR-02.)

#### Scenario: Unauthenticated delegation refused
- **WHEN** a request without a valid realm-signed delegation bearer reaches the
  delegation receiver
- **THEN** it is refused with 401 before parsing and no pending-approval state is
  created
