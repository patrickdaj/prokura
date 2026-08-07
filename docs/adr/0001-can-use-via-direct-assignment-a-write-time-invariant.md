# ADR-0001: can_use via direct assignment + a write-time invariant

- **Status:** accepted
- **Source of truth:** SPEC-REVIEW F1; `openspec/specs/per-agent-consent/spec.md`; `deploy/openfga/model.fga`
- **Relationship:** **Supersedes** the original SPEC.md §5 `can_use` intersection construct.
- **Also records the locked choice:** Sole-tuple-writer / operator==owner invariant (F1).

## Context

SPEC.md §5 defined `can_use: [agent] and operator from can_use` — self-referential (OpenFGA rejects it) and, even if loaded, unsatisfiable (the two branches yield different subject types). The intent — an agent may use a grant only if the agent's operator owns it — is a cross-object join OpenFGA cannot express.

## Decision

Model `can_use: [agent]` as direct assignment. The token broker is the **sole writer** of `can_use` tuples and enforces `agent.operator == grant.owner` at write time. A security property moves from the model into broker code, so the broker is a trusted tuple writer in the threat model.

## Alternatives considered

- B — two separate FGA checks in broker code (owner==sub, operator==sub): loses per-agent consent granularity.
- C — Auth0-style, no FGA gate on grants: simplest, matches the commercial product, forfeits per-agent consent (a Prokura differentiator).

## Consequences

Keeps the per-agent-consent story and is honest about where enforcement lives. Downside: the invariant is code-enforced, not model-enforced — named as a trusted-code assumption in the threat model (attack tree 2).

