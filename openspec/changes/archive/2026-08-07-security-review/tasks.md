# Tasks — Security Review

> Executed on `apply`, **after M6**. Each task produces evidence (test citation,
> config/code `file:line`, or a documented probe) and a finding disposition
> (`fix` | `accepted-residual` | `spec-gap` | `test-gap`). Re-confirm all cited
> locations against the then-current tree — do not assume today's line numbers.

## 1. Scope freeze and harness

- [x] 1.1 Confirm M1–M5 + MCP milestone are archived and the compose stack builds; pin the commit the review runs against
- [x] 1.2 Bring up the full stack and confirm all TCB services (Keycloak, broker, approval, tools-api, OpenFGA, OpenBao) and the telemetry pipeline are healthy
- [x] 1.3 Run the existing `tests/smoke/` suite green as the evidence baseline; record which invariants each test already covers
- [x] 1.4 Create the findings register (id, invariant, evidence, severity, disposition) and the `{service × requirement}` / `{flow × requirement}` coverage matrix from design.md

## 2. TCB and trust boundaries (baseline: TCB explicit and minimal)

- [x] 2.1 Enumerate every component and confirm the TCB set matches the spec (Keycloak, broker, approval, OpenFGA, OpenBao); confirm agents, MCP clients, ntfy, tools-api execution surface are outside it
- [x] 2.2 Verify a freshly DCR-registered MCP client gains no grant access without a `can_use` tuple (registration ≠ trust)
- [x] 2.3 Confirm no component outside the TCB is relied on to enforce any invariant; log deviations

## 3. Inter-service authentication (baseline: every state-changing call authenticated)

- [x] 3.1 Enumerate every externally reachable endpoint of every TCB service; mark which mutate credential/consent/approval state
- [x] 3.2 Broker: verify JWKS signature check + `aud=token-broker` enforcement; probe unauthenticated and wrong-audience requests → expect 401/403, no provider token
- [x] 3.3 Approval service: verify CIBA decision accepted only over Keycloak's delegation-authorized callback; probe a forged decision POST → expect rejection
- [x] 3.4 tools-api: verify action execution requires a valid action token; probe without one → expect rejection
- [x] 3.5 Confirm no state-mutating endpoint accepts an anonymous request across all TCB services

## 4. Secret confidentiality (baseline: secrets never leave their store)

- [x] 4.1 Exercise every TCB endpoint on success AND error paths; grep responses, logs, and audit records for refresh credentials, client secrets, OpenBao tokens (extend `test_no_provider_token_in_logs` coverage)
- [x] 4.2 Verify refresh credentials exist only in OpenBao and only transiently in broker memory during refresh; confirm broker OpenBao token is scoped to `secret/data/grants/*`
- [x] 4.3 Scan repo + compose files for committed secrets; confirm only documented non-production dev values are present
- [x] 4.4 Confirm provider access tokens are returned only to the caller they were minted for and never logged

## 5. Token lifetime and exchange (baseline: bounded TTL, non-wildcard exchange)

- [x] 5.1 Inspect Keycloak realm export: confirm delegated + broker-audience token lifespans ≤15 min
- [x] 5.2 Verify broker hand-out returns `expires_in ≤ 900` for every provider; confirm the TTL table states real residual validity honestly
- [x] 5.3 Confirm token exchange is permitted per `(client, audience)` pair only — no wildcard; probe an unlisted audience → expect refusal
- [x] 5.4 Verify an agent cannot obtain Keycloak's stored provider read-token directly; only the broker re-exchanging as its confidential client can

## 6. Per-agent consent and tuple-writer invariant (baseline: end-user authz + code-enforced invariant)

- [x] 6.1 Confirm OpenFGA model uses `define can_use: [agent]` direct assignment with no cross-object joins; model loads
- [x] 6.2 Verify the broker is the sole `can_use` tuple writer and enforces `operator == owner`; probe a cross-user write → expect refusal + log
- [x] 6.3 Verify consent revocation deletes the tuple and takes effect on the next broker request
- [x] 6.4 Flag operator==owner as a trusted-code assumption for the threat model

## 7. Approval flow integrity (baseline: input hygiene + replay resistance)

- [x] 7.1 Verify `binding_message` carries only a reference ID matching `^[a-zA-Z0-9-._+/!?#]{1,50}$`; no free-text agent prose anywhere in the flow
- [x] 7.2 Verify the approval UI renders the service-held payload, never agent-authored text; confirm payload hash recorded at registration
- [x] 7.3 Verify hash-verified execution: parameter mismatch → refused; consumed reference ID replay → refused
- [x] 7.4 Verify a spoofed ntfy notification is inert and leaks no action parameters (deep link + reference ID only)
- [x] 7.5 Verify denial and 120 s timeout abort cleanly with no action token issued

## 8. Data-access authorization (baseline: evaluated as end user)

- [x] 8.1 Verify RAG/tool reads evaluate the FGA check with the end user as subject, never the agent principal
- [x] 8.2 Adversarial: confirm a document accessible to the agent principal but not the delegating user is excluded from results
- [x] 8.3 Confirm FGA tuples mirror the Drive-backed corpus ACLs (no drift that would over-share)

## 9. Audit and observability (baseline: audit completeness with correlation)

- [x] 9.1 Verify every issuance, denial, and approval decision produces an audit record with `{user, agent, action/provider, scopes, ttl/outcome}` + correlation ID
- [x] 9.2 Verify each audit event is queryable live (Loki) within seconds and shares one correlation ID across Keycloak/broker/approval for a single flow
- [x] 9.3 Identify any security-relevant event that is not audited

## 10. Input validation and error hygiene (baseline: external surfaces leak nothing)

- [x] 10.1 Fuzz/probe each external endpoint with malformed, oversized, and unexpected input → expect generic rejection, no stack trace/internal path/secret
- [x] 10.2 Force an upstream provider/store error → confirm the caller receives a sanitized error, not the raw upstream body
- [x] 10.3 Review error handlers across services for leaked internal detail

## 11. Non-production posture (baseline: honest residual risk)

- [x] 11.1 Confirm docs state the non-production posture (single-node, dev secrets, no mTLS, no HA) explicitly
- [x] 11.2 Enumerate accepted residual risks (broker single point of trust, dev secrets, no mTLS) and record each as an accepted-residual disposition with its named mitigation
- [x] 11.3 List every code-enforced (vs model/config-enforced) invariant as a trusted-code assumption

## 12. Synthesis and handoff

- [x] 12.1 Consolidate the findings register; assign severity by exploitability within the non-production posture
- [x] 12.2 For each `test-gap`, file the missing `tests/smoke/` case (or a follow-up task); for each `spec-gap`, open a follow-up delta change against the affected capability spec
- [x] 12.3 Hand off control weaknesses to `expand-threat-model` (as attack paths) and decision rationales to `adr-reconciliation` (as ADR pointers)
- [x] 12.4 Write the review summary; confirm every `security-baseline` requirement has a recorded disposition (no invariant left unchecked)
