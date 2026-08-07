# Tasks — Expand Threat Model

> Executed on `apply`, **after M6** and ideally after `security-review` (its
> findings feed the attack trees). Output is the expanded `docs/threat-model.md`
> meeting every `threat-model` spec acceptance criterion.

## 1. Inputs and framing

- [ ] 1.1 Read the current `docs/threat-model.md` (M2 draft); mark the TCB statement and TTL table as content to preserve
- [ ] 1.2 Pull inputs: `security-review` findings register, SPEC.md §9/§11, SPEC-REVIEW F1–F9/Q1–Q7, the security-baseline spec
- [ ] 1.3 Confirm the TCB set matches the `security-baseline` spec; note any drift to reconcile

## 2. Assets and actors

- [ ] 2.1 Enumerate protected assets (user identity, delegated tokens, refresh credentials, provider access tokens, `can_use` tuples, approval payloads/tokens, RAG corpus, audit records); for each state its store, owning TCB component, and compromise impact
- [ ] 2.2 Enumerate actors and classify each inside/outside the TCB

## 3. Attacker model

- [ ] 3.1 Define each adversary class with assumed capabilities and boundaries: compromised agent, malicious MCP/DCR client, on-network attacker, malicious grant-linking user, curious insider
- [ ] 3.2 State the compose-network assumptions (no mTLS, shared network) so on-network threats are grounded

## 4. Trust boundaries

- [ ] 4.1 Draw the trust-boundary view: label every credential/data crossing (agent→broker, broker→OpenBao, broker→provider, Keycloak↔approval, agent→tools-api, MCP-client→MCP-server) with direction of trust
- [ ] 4.2 Verify every flow's boundary crossings appear in the view

## 5. STRIDE per flow

- [ ] 5.1 Flow A (delegated token): STRIDE table, every category a threat+mitigation or reasoned N/A
- [ ] 5.2 Flow B (token brokering): STRIDE table — emphasize scope over-broadening, tuple bypass, credential disclosure
- [ ] 5.3 Flow C (human approval): STRIDE table — emphasize binding-message tampering (F5), notification spoofing (F7), replay (F8)
- [ ] 5.4 Flow D (RAG): STRIDE table — emphasize confused-deputy / information disclosure (§11)
- [ ] 5.5 MCP authorization surface: STRIDE table — DCR self-registration, metadata integrity, documented RFC 8707 gap
- [ ] 5.6 Review all five grids for empty cells; fill or justify N/A

## 6. Attack trees for high-value targets

- [ ] 6.1 Token-broker compromise: root-to-leaf paths, blast radius (all grants + sole tuple writer), least-privilege mitigations that bound it
- [ ] 6.2 `can_use` tuple forgery / cross-user write: paths, the operator==owner code-enforced control, and its trusted-code assumption
- [ ] 6.3 Approval spoofing/replay: paths through notification, binding message, and consumed-ID reuse; controls that break each
- [ ] 6.4 RAG confused-deputy over-sharing: paths, the end-user-evaluated authz control, and the acknowledged §11 residual

## 7. Threat → disposition mapping

- [ ] 7.1 Map each threat to a mitigating control (cite security-baseline requirement / spec scenario / code or config) or to the residual-risk register
- [ ] 7.2 Verify no orphan threats (every threat has a disposition)

## 8. Residual-risk register

- [ ] 8.1 List accepted residuals (no mTLS, dev secrets, single-node, broker concentration, stretched mock-provider session); for each give the acceptance rationale and the production alternative
- [ ] 8.2 Cross-check residuals against `security-review` accepted-residual findings for consistency

## 9. Assemble and retire the draft

- [ ] 9.1 Compose the expanded `docs/threat-model.md`: preserve TCB statement + TTL table, add all sections above, remove the "M6 deliverable" deferral header
- [ ] 9.2 Add cross-references: threats ↔ security-baseline controls, mitigations ↔ ADRs (for `adr-reconciliation`)
- [ ] 9.3 Validate against the `threat-model` spec: assets, attacker model, boundaries, five STRIDE grids, four attack trees, complete disposition mapping, residual register all present
- [ ] 9.4 Hand off: decisions behind mitigations → `adr-reconciliation`; any newly discovered requirement gap → its own follow-up delta change
