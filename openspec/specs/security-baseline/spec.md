# security-baseline

## Purpose

The cross-cutting, system-wide security invariants the Prokura reference architecture asserts and the M6 security review verifies — TCB definition, inter-service authentication, secret confidentiality, token-lifetime ceilings, non-wildcard token exchange, end-user-evaluated data authorization, audit completeness with correlation, input/error hygiene, and honest disclosure of the non-production posture and residual risk. Distinct from per-capability security requirements, which stay in their own specs; this baseline references, not duplicates, them. Verified in [docs/security-review.md](../../../docs/security-review.md).

## Requirements

### Requirement: Trusted Computing Base is explicit and minimal

The system SHALL name every component that can mint, broker, gate, or store credentials as part of a Trusted Computing Base (TCB), and everything outside it SHALL be treated as untrusted. The TCB is Keycloak, the token broker, the approval service, OpenFGA, and OpenBao. Agents, MCP clients, notification transport (ntfy), and the demo tools-api's action-execution surface are outside the TCB. Any component added to the TCB SHALL be justified in the threat model.

#### Scenario: TCB is documented and closed
- **WHEN** the threat model and security-baseline are reviewed together
- **THEN** every credential-minting, -brokering, -gating, or -storing component appears in the named TCB, and no component outside the TCB is relied on to enforce a security invariant

#### Scenario: Untrusted client cannot self-elevate
- **WHEN** an MCP client registers itself via dynamic client registration
- **THEN** it gains no access to any user grant until a `can_use` consent tuple is written for it, i.e. registration alone confers no TCB trust

### Requirement: Every state-changing inter-service call is authenticated

Every request that crosses a service boundary and mints, brokers, or acts on a credential SHALL be authenticated, and the receiver SHALL verify the caller's identity before acting. The broker SHALL verify bearer-token signature against Keycloak JWKS and the `aud=token-broker` audience; the approval service SHALL accept CIBA decisions only over Keycloak's delegation-authorized callback; the tools-api SHALL require a valid action token. No externally reachable endpoint SHALL mutate credential or approval state without authentication.

#### Scenario: Unauthenticated broker request refused
- **WHEN** a request reaches any broker token-issuance endpoint without a valid Keycloak-signed, correctly-audienced bearer token
- **THEN** the broker refuses with 401/403 and issues no provider token

#### Scenario: No anonymous state mutation
- **WHEN** every externally reachable endpoint of every TCB service is enumerated
- **THEN** none that mutates credential, consent, or approval state accepts an unauthenticated request

### Requirement: Secrets never appear outside their store

Long-lived provider credentials SHALL exist only inside OpenBao and reside in service memory only transiently during a refresh. No secret — refresh credential, client secret, OpenBao token, or provider access token beyond the caller it was minted for — SHALL appear in any API response body, log line, audit record, error message, stack trace, or file committed to the repository. Development secrets used by compose SHALL be confined to `.env` / dev-mode tokens and documented as non-production.

#### Scenario: Secret absent from all outputs including error paths
- **WHEN** any TCB service endpoint is exercised on both success and failure paths
- **THEN** no response body, log line, or audit record contains a stored refresh credential, client secret, or OpenBao token

#### Scenario: Repository contains no committed secret
- **WHEN** the repository and compose files are scanned
- **THEN** the only credentials present are documented non-production dev values, and no production secret is committed

### Requirement: Agent-held tokens have a bounded lifetime

Every token an agent can hold SHALL have a TTL of at most 15 minutes: Keycloak-issued delegated and broker-audience tokens SHALL be capped at ≤15 minutes, and the broker's provider-token hand-out interval SHALL return `expires_in ≤ 900`. Residual provider-side validity beyond the hand-out interval is provider-controlled and SHALL be stated honestly in the TTL table, never misrepresented as 15 minutes.

#### Scenario: Issued token respects the ceiling
- **WHEN** any agent-held token is issued by Keycloak or the broker
- **THEN** its lifetime (or `expires_in`) is at most 900 seconds

#### Scenario: Residual validity stated honestly
- **WHEN** a provider token with longer real validity is handed out
- **THEN** the hand-out interval is still ≤900 s and the true residual validity is documented in the TTL table rather than claimed to be 15 minutes

### Requirement: Token exchange is never wildcarded

Delegated token exchange SHALL be explicitly permitted per `(client, audience)` pair in Keycloak. No configuration SHALL permit an agent client to exchange for an arbitrary audience, and in particular an agent SHALL NOT be able to obtain a token for any audience other than the ones its policy allows (broker audience for Flow B; never the provider read-token audience directly).

#### Scenario: Unlisted audience refused
- **WHEN** an agent client requests a token exchange for an audience not explicitly permitted for it
- **THEN** Keycloak refuses the exchange

#### Scenario: Provider read-token audience unreachable to agents
- **WHEN** an agent attempts to exchange for or otherwise obtain Keycloak's stored provider read-token directly
- **THEN** it cannot; only the broker, re-exchanging as its confidential client, can retrieve the stored credential

### Requirement: Data-access authorization is evaluated as the end user

For any access to user data (RAG retrieval and tool reads over user resources), the fine-grained authorization check SHALL be evaluated with the end user as the subject, never with the agent principal as subject. An agent SHALL NOT be able to widen its data reach beyond what the delegating user could access.

#### Scenario: Filtering uses the user subject
- **WHEN** an agent performs an FGA-filtered retrieval on the user's behalf
- **THEN** the FGA check subject is the end user, and results exclude any document the user cannot access

#### Scenario: Agent cannot exceed user reach
- **WHEN** a document is accessible to the agent's own principal but not to the delegating user
- **THEN** the document is excluded from results

### Requirement: Every credential and approval decision is audit-logged with correlation

Every token issuance, every denial, and every approval or denial decision SHALL produce an audit record carrying at least `{user, agent, action-or-provider, scopes, ttl-or-outcome}` and a correlation ID that links the related Keycloak, broker, and approval events, and each SHALL also be emitted to the telemetry pipeline in realtime under the same correlation ID.

#### Scenario: Issuance and denial both audited
- **WHEN** a provider token is issued or a request is denied
- **THEN** an audit record with the full field set and a correlation ID exists and is queryable live within seconds

#### Scenario: Correlation joins the flow
- **WHEN** a single delegation flow spans Keycloak, broker, and approval events
- **THEN** those events share one correlation ID and are joinable in the trace

### Requirement: External surfaces validate input and leak nothing on error

Every externally reachable endpoint SHALL validate and bound its inputs and SHALL NOT return internal implementation detail (stack traces, internal hostnames, secret material, raw upstream errors) in error responses. Malformed, oversized, or unexpected input SHALL be rejected with a generic error rather than processed or reflected.

#### Scenario: Malformed input rejected cleanly
- **WHEN** a malformed or oversized request is sent to any TCB-service endpoint
- **THEN** it is rejected with a generic error carrying no stack trace, internal path, or secret

#### Scenario: Upstream error not reflected verbatim
- **WHEN** an upstream provider or store returns an error during a request
- **THEN** the caller receives a sanitized error, not the raw upstream body

### Requirement: Non-production posture and residual risk are stated honestly

The deployment SHALL be documented as non-production (single-node compose, dev-mode secret store, no mTLS between services, no HA), and the security-baseline SHALL enumerate the residual risks this posture accepts rather than implying they are mitigated. Any invariant enforced in service code rather than in a declarative model (e.g. the broker's sole-tuple-writer / operator==owner check) SHALL be named as a trusted-code assumption.

#### Scenario: Residual risks are listed, not hidden
- **WHEN** the security-baseline and threat model are reviewed
- **THEN** the accepted residual risks (dev secrets, no mTLS, single point of trust in the broker) are explicitly listed as accepted, non-production trade-offs

#### Scenario: Code-enforced invariants are named
- **WHEN** a security invariant is enforced in service code rather than in the FGA model or Keycloak config
- **THEN** it is documented as a trusted-code assumption whose compromise the review accounts for
