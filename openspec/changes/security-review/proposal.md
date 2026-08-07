## Why

Prokura's product *is* its trustworthiness: the reference architecture is only credible if the security properties it claims are actually enforced and demonstrably so. Security requirements today are scattered across per-capability specs (`token-brokering`, `human-approval`, `per-agent-consent`) and SPEC.md §9's "hard rules", with no single contract asserting the cross-cutting invariants nor any end-to-end pass confirming the assembled system upholds them. This change delivers M6's security-review deliverable: consolidate the cross-cutting security requirements into one `security-baseline` spec and run a structured end-to-end review of every service and flow against it.

This is the first of three M6 ("Polish") follow-ups. The other two — `expand-threat-model` (adversary-centric STRIDE-per-flow) and `adr-reconciliation` (decisions → `docs/adr/`) — are separate changes. This change is **control-centric**: does the built system enforce its own hard rules? The threat-model change is **adversary-centric**: what can an attacker do to each flow? The two are complementary and cross-reference each other.

## What Changes

- **New `security-baseline` capability spec** consolidating the cross-cutting security invariants that no single capability owns: TCB membership, inter-service authentication, secret handling (no secrets in logs/responses/repo), token TTL ceilings, no-wildcard token exchange, FGA-evaluated-as-end-user, audit completeness, input validation and error hygiene on every externally reachable surface. Seeded from SPEC.md §9 and the F1–F9 / Q1–Q7 decisions, formalized with verifiable scenarios.
- **An end-to-end review methodology** (`design.md`): scope, the per-service and per-flow checklist, how findings are classified (severity, exploitability given the non-production compose posture) and triaged, and the explicit boundary with the `expand-threat-model` change so the two don't duplicate.
- **A review task checklist** (`tasks.md`): every TCB service (Keycloak config, token broker, approval service, tools-api, OpenFGA model, OpenBao policy) and every flow (A delegation, B brokering, C approval, D RAG) audited against the baseline, with findings and remediation tracked as tasks. **Findings are produced when this change is applied — after M6 — not now.**
- **No production hardening is promised**: the compose deployment stays explicitly non-production. The review states residual risks honestly (dev secrets, no mTLS, single-node) rather than pretending to fix them.

## Capabilities

### New Capabilities
- `security-baseline`: The cross-cutting, system-wide security invariants the Prokura reference architecture asserts and the review verifies — TCB definition, inter-service authN/authZ, secret confidentiality, token-lifetime ceilings, non-wildcard exchange, end-user-evaluated data authorization, audit completeness, and input/error hygiene. Distinct from per-capability security requirements, which stay in their own specs.

### Modified Capabilities
<!-- None pre-declared. The review may surface requirement-level gaps in existing specs
     (token-brokering, human-approval, per-agent-consent, identity-delegation,
     rag-authorization, observability). Any such gap is recorded as a review finding and,
     if it warrants a spec change, handled as its own delta rather than pre-empted here. -->

## Impact

- **Specs**: adds `openspec/specs/security-baseline/` on archive; may generate follow-up delta changes for existing specs if the review finds requirement gaps.
- **Services reviewed** (no code changes until applied): `services/token-broker`, `services/approval`, `services/tools-api`, `services/console`, plus Keycloak realm config, OpenFGA model, and OpenBao policies.
- **Docs**: findings cross-reference `docs/threat-model.md` (expanded by the sibling change) and feed `docs/adr/` (populated by the sibling change).
- **Dependencies**: none new. Review uses existing smoke tests (`tests/smoke/`) as evidence and identifies coverage gaps.
- **Sequencing**: planning artifacts (this pass) are authored now; the review itself (`apply`) runs after M6 completes, so it audits the finished architecture.
