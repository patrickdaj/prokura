# Design — Security Review

## Context

This change runs an end-to-end, **control-centric** security review of the assembled Prokura reference architecture and formalizes the cross-cutting `security-baseline` capability the review checks against. It is one of three M6 ("Polish") deliverables; the other two are separate changes (`expand-threat-model`, `adr-reconciliation`). The review is planned now but **executed on `apply`, after M6**, so it audits the finished system (M1–M5 plus the MCP milestone) rather than a moving target.

The system under review is the docker-compose stack: Keycloak (IdP/AS, MCP AS), token broker (FastAPI), approval service (FastAPI + CIBA HTTP channel), tools-api (action execution + hash/replay enforcement), console, OpenFGA (authorization model), OpenBao (secret store), and the supporting telemetry pipeline. The deployment is explicitly non-production; the review's job is to confirm the *claimed* invariants hold and to state accepted residual risk honestly — not to certify production readiness.

## Goals / Non-Goals

**Goals**
- Verify each `security-baseline` requirement is actually enforced, with evidence (a passing test, a config assertion, or a manual probe) per invariant.
- Cover every TCB service and every core flow (A delegation, B brokering, C approval, D RAG) plus the MCP authorization surface.
- Produce a findings register (severity, evidence, remediation, or accepted-residual disposition) that feeds `docs/threat-model.md` and `docs/adr/`.
- Identify test-coverage gaps where an invariant is asserted but not exercised by `tests/smoke/`.

**Non-Goals**
- No production hardening (mTLS, secret rotation, HA) — those stay documented residual risks per the non-production posture.
- No adversary-centric STRIDE-per-flow enumeration — that is the sibling `expand-threat-model` change (see Boundary below).
- No ADR authoring — that is the sibling `adr-reconciliation` change.
- No new capabilities or product behavior; findings that imply a spec change are logged and handled as their own follow-up deltas.

## Boundary with the sibling M6 changes

The three M6 changes are deliberately non-overlapping:

| Change | Lens | Output |
|--------|------|--------|
| `security-review` (this) | **Control-centric**: are the hard rules enforced? | `security-baseline` spec + findings register with evidence per invariant |
| `expand-threat-model` | **Adversary-centric**: STRIDE per flow, attack trees, what an attacker can do | expanded `docs/threat-model.md` |
| `adr-reconciliation` | **Decision-centric**: is every locked decision recorded? | `docs/adr/*` derived from OpenSpec |

Cross-references, not duplication: a review finding that a control is weak becomes an attack path the threat model elaborates; a control whose rationale is a locked decision (F1–F9 / Q1–Q7) points at the ADR that records it. The review consumes the current `docs/threat-model.md` TTL table and TCB statement as inputs rather than re-deriving them.

## Review method

**Framework.** Each `security-baseline` requirement is a checklist line. For each, the reviewer establishes one of three evidence types, in preference order:
1. **Test evidence** — an existing `tests/smoke/` case demonstrates the invariant (cite the test). Where the assertion exists but no test does, log a coverage-gap finding.
2. **Config/code assertion** — the invariant is enforced by a named config value or code path (cite file:line), e.g. Keycloak token-lifespan settings, the broker's `aud` check, the OpenBao policy scope.
3. **Manual probe** — a documented request/inspection confirming the behavior (used for negative cases like "malformed input rejected without stack trace").

**Coverage matrix.** The review is organized as `{service × baseline-requirement}` and `{flow × baseline-requirement}` so no service or flow is checked against a partial rule set. Per-service passes read the actual artifacts: Keycloak realm export (token lifespans, exchange permits, client scopes, DCR settings), broker code (validation chain, sole-tuple-writer invariant, OpenBao token scope), approval service (payload hashing, single-use/replay, CIBA callback auth), tools-api (hash-verified execution, consumed-ID rejection), OpenFGA model (`can_use` direct assignment, no cross-object joins), OpenBao policies (path scoping).

**Finding classification.** Severity reflects exploitability *within the intended non-production posture*: a missing mTLS link is an accepted residual (informational), while a secret leaking into a log or an agent reaching the provider read-token audience is high. Each finding records: id, invariant, evidence, severity, and disposition (`fix` | `accepted-residual` | `spec-gap` | `test-gap`).

## Key decisions

- **`security-baseline` is a new capability, not edits to existing specs.** The cross-cutting invariants (TCB, inter-service authN, secret confidentiality, TTL ceiling, non-wildcard exchange, end-user data authz, audit, input hygiene, honest residual risk) have no single owning capability today — they live implicitly in SPEC.md §9 and scattered scenarios. Consolidating them into one contract makes the review checklist a spec rather than an ad-hoc list. Per-capability security requirements stay in their own specs; the baseline references, not duplicates, them.
- **Execute on apply, after M6.** Reviewing before the architecture is complete would produce findings against code that is still changing. Authoring the plan now (this pass) fixes the contract and checklist; running it later audits the real thing.
- **Honesty over theater.** The non-production posture is a stated design constraint, so the review's success criterion is *accurate disclosure of residual risk*, not zero findings. An "accepted-residual" disposition is a valid, first-class outcome.

## Risks / Trade-offs

- **Broker is a single high-value point of trust** (sole tuple writer + holds all refresh credentials). The review confirms its least-privilege posture (OpenBao token scoped to `secret/data/grants/*`, operator==owner write check) and records the concentration as an accepted residual with the mitigations named — it cannot eliminate the concentration in a single-node reference.
- **Code-enforced invariants** (operator==owner) are only as strong as the broker code; the review flags every such invariant as a trusted-code assumption so the threat model can reason about broker compromise.
- **Evidence drift**: because the review runs after M6, cited file:line and test names must be re-confirmed at apply time; tasks are written to re-verify against the then-current tree rather than assume today's line numbers.

## Migration / Rollout

None — this change adds a spec and a review, not runtime behavior. On archive, `security-baseline` joins `openspec/specs/`; the findings register lands as review output and seeds the sibling threat-model and ADR changes.
