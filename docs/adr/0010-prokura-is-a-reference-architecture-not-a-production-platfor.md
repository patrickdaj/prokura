# ADR-0010: Prokura is a reference architecture, not a production platform

- **Status:** accepted
- **Source of truth:** SPEC-REVIEW Q1; `README.md`; `docs/security-review.md`
- **Also records the locked choice:** Non-production docker-compose posture (Q1).

## Context

The spec oscillated between 'reference implementation', production-grade §9 hard rules, and docker-compose-only. Where polish goes depends on the answer.

## Decision

Prokura is a **reference architecture**: the docs, ADRs, threat model, and demo *are* the product. §9 rules are stated as 'what production would require'; the compose stack is explicitly non-production. Residual risks are disclosed, not fixed.

## Alternatives considered

- B — a runnable platform people deploy: then SDK ergonomics, rotation, HA belong in scope; the milestone plan isn't credible.
- C — a portfolio/credibility piece: demo + README polish outrank breadth.

## Consequences

Cheapest path to credibility; matches the §2 non-goals. Drives the honesty discipline in the security review and threat model.

