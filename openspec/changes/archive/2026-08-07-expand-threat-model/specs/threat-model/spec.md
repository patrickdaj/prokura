## ADDED Requirements

### Requirement: Assets and actors are enumerated

The threat model SHALL enumerate the protected assets (user identity, delegated agent tokens, third-party refresh credentials, provider access tokens, `can_use` consent tuples, approval action payloads/tokens, RAG corpus contents, audit records) and the participating actors, classifying each actor as inside or outside the TCB.

#### Scenario: Every asset has an owner and a store
- **WHEN** the assets section is reviewed
- **THEN** each named asset states where it lives, which TCB component owns it, and what its compromise would enable

### Requirement: Explicit attacker model

The threat model SHALL define each adversary class with its assumed capabilities and boundaries: malicious or compromised agent, malicious MCP client (self-registered via DCR), on-network attacker inside the compose network, malicious grant-linking user, and curious/malicious insider. Every STRIDE entry SHALL be evaluated against at least one defined adversary; no threat SHALL assume an undefined attacker.

#### Scenario: Threats reference a defined adversary
- **WHEN** any threat in the model is examined
- **THEN** it names which adversary class it applies to, and that class appears in the attacker model with stated capabilities

#### Scenario: DCR client is modeled as untrusted
- **WHEN** the MCP authorization surface is analyzed
- **THEN** a self-registered client is treated as an untrusted adversary whose only gate to user grants is the `can_use` consent tuple

### Requirement: Trust boundaries are drawn explicitly

The threat model SHALL contain a trust-boundary view identifying every boundary crossing where data or credentials pass between a less-trusted and a more-trusted component (agent→broker, broker→OpenBao, broker→provider, Keycloak↔approval-service, agent→tools-api, MCP-client→MCP-server). The TCB set SHALL match the `security-baseline` spec.

#### Scenario: Boundary crossings are covered
- **WHEN** the trust-boundary view is compared to the flows
- **THEN** every inter-component credential or data crossing appears as a labeled boundary with the direction of trust noted

### Requirement: STRIDE analysis per flow

The threat model SHALL provide a STRIDE analysis (Spoofing, Tampering, Repudiation, Information disclosure, Denial of service, Elevation of privilege) for each core flow — A (delegated token), B (token brokering), C (human approval), D (FGA-filtered RAG) — and for the MCP authorization surface. Each STRIDE category per flow SHALL either identify a concrete threat with its mitigation or state, with reasoning, that the category does not apply.

#### Scenario: No empty STRIDE cells
- **WHEN** the STRIDE table for any flow is reviewed
- **THEN** every one of the six categories is either a concrete threat+mitigation or an explicit, reasoned "not applicable"

#### Scenario: MCP surface included
- **WHEN** the STRIDE coverage is enumerated
- **THEN** the MCP authorization server surface (DCR, metadata, the documented RFC 8707 gap) has its own STRIDE analysis

### Requirement: Attack trees for high-value targets

The threat model SHALL contain an attack tree for each highest-value target: token-broker compromise, `can_use` tuple forgery/cross-user write, approval spoofing or replay, and RAG confused-deputy over-sharing. Each tree SHALL trace at least one root-to-leaf path and annotate which control breaks that path.

#### Scenario: Each high-value target has a tree with a breaking control
- **WHEN** an attack tree is examined
- **THEN** it shows at least one attack path and names the control (or accepted residual) that interrupts it

#### Scenario: Broker-compromise blast radius stated
- **WHEN** the broker-compromise tree is reviewed
- **THEN** it states the blast radius (all grants, sole tuple writer) and the least-privilege mitigations that bound it

### Requirement: Every threat maps to a mitigation or an accepted residual

Each identified threat SHALL be mapped either to a mitigating control (citing the `security-baseline` requirement, spec scenario, or code/config that enforces it) or to an explicitly accepted residual risk. No threat SHALL be left with an unstated disposition.

#### Scenario: No orphan threats
- **WHEN** the full threat list is reviewed
- **THEN** each threat links to a named control or is recorded in the residual-risk register with a rationale

### Requirement: Residual-risk register for the non-production posture

The threat model SHALL maintain a residual-risk register listing risks the non-production posture accepts (no mTLS, dev-mode secrets, single-node, broker as concentrated point of trust, stretched mock-provider session lifetime), each with the reason it is accepted and what a production deployment would do instead.

#### Scenario: Residuals are explicit, not implied
- **WHEN** the residual-risk register is reviewed
- **THEN** each accepted risk states why it is acceptable for a non-production reference and the production alternative

### Requirement: Findings are communicated in a reader-facing narrative

Beyond the rigorous reference model, the project SHALL publish a reader-facing
findings narrative (a milestone-series blog post) that presents the model's headline
results — at minimum the four high-value attack targets (token-broker compromise,
`can_use` tuple forgery, approval spoofing/replay, RAG confused-deputy) — and, for
each, the control that breaks the attack path or the residual risk that is accepted
and why. The narrative SHALL cross-link the full `docs/threat-model.md` and remain
consistent with it (no finding stated in the narrative that the model does not
support).

#### Scenario: Headline attack paths are narrated with their defense
- **WHEN** the findings narrative is read
- **THEN** each of the four high-value targets is presented with its most important
  attack path and the specific control (or accepted residual) that addresses it, and a
  link into the corresponding section of `docs/threat-model.md`

### Requirement: Preserves and supersedes the M2 working draft

The expanded threat model SHALL preserve the existing TCB statement and per-provider TTL-honesty table from the M2 draft, and SHALL remove the draft's "M6 deliverable" deferral header once the full model exists.

#### Scenario: Draft content carried forward
- **WHEN** the expanded model is compared to the M2 draft
- **THEN** the TCB statement and TTL table are present (extended, not dropped) and the working-draft deferral notice is gone
