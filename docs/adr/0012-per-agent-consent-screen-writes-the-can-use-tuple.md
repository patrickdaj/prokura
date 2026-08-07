# ADR-0012: Per-agent consent screen writes the can_use tuple

- **Status:** accepted
- **Source of truth:** SPEC-REVIEW Q3; `openspec/specs/per-agent-consent/spec.md`; `services/token-broker/consent.py`

## Context

The Flow B FGA gate checked `can_use` tuples with no defined provisioning path or consent semantics.

## Decision

Grant setup / first use shows a **per-agent consent screen** ('Allow *summarizer-agent* to use your GitHub grant — [scopes]'); approval writes the `can_use` tuple (via the broker, ADR-0001). More granular than Auth0's app-scoped consent, and it gives the FGA grant model a reason to exist.

## Alternatives considered

- A — implicit: grant setup authorizes all the user's agents (coarse).
- C — admin-provisioned tuples: wrong for the self-service demo.

## Consequences

Per-agent consent is a Prokura differentiator. Consent + the operator==owner write check together bound cross-user forgery.

