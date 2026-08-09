# security-baseline — delta (close-correct-party-gaps / M7)

## MODIFIED Requirements

### Requirement: Every state-changing inter-service call is authenticated

Every request that crosses a service boundary and mints, brokers, or acts on a credential SHALL be authenticated, and the receiver SHALL verify the caller's identity before acting. The broker SHALL verify bearer-token signature against Keycloak JWKS and the `aud=token-broker` audience; the approval service SHALL accept CIBA decisions only over Keycloak's delegation-authorized callback, and its CIBA delegation receiver SHALL authenticate Keycloak's delegation POST (verifying the delegation bearer as a realm-signed JWT from its own CIBA client) and bound its body size before parsing (SR-02 closed, not accepted); the tools-api SHALL require a valid action token. Human-facing decision and consent surfaces SHALL authenticate via an OIDC browser session — never a URL-carried bearer token. No externally reachable endpoint SHALL mutate credential, consent, or approval state without authentication.

#### Scenario: Unauthenticated broker request refused
- **WHEN** a request reaches any broker token-issuance endpoint without a valid Keycloak-signed, correctly-audienced bearer token
- **THEN** the broker refuses with 401/403 and issues no provider token

#### Scenario: Unauthenticated CIBA delegation refused
- **WHEN** a delegation POST without a valid realm-signed delegation bearer reaches the approval service's CIBA receiver
- **THEN** it is refused with 401 before parsing and no pending approval is created

#### Scenario: No anonymous state mutation
- **WHEN** every externally reachable endpoint of every TCB service is enumerated
- **THEN** none that mutates credential, consent, or approval state accepts an unauthenticated request, and none accepts a URL-carried bearer token as authentication

## ADDED Requirements

### Requirement: Agent-side code holds no human credentials or human capabilities
No agent-facing client, SDK path, or agent-side test helper SHALL possess user
passwords, hold the CIBA grant, or call decision/consent endpoints. Simulated
humans in tests SHALL be confined to explicitly-labeled UI-driving helpers that
exercise the real login and the real surfaces; an automated invariant SHALL
verify the separation (agent-side kits contain no user credential and no call to
decide, consent, or backchannel-authentication endpoints).

#### Scenario: Separation invariant holds
- **WHEN** the invariant check runs over the agent-side kits and SDK
- **THEN** it finds no user credential, no CIBA initiation, and no
  decision/consent call outside the labeled human-simulation kit

#### Scenario: Error text does not leak internals (SR-01 closed)
- **WHEN** any TCB service maps an upstream failure into a client-facing error
- **THEN** the response carries only a stable error code, with the upstream
  detail confined to server-side audit logs
