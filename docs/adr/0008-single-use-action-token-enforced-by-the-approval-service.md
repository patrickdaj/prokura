# ADR-0008: Single-use action token enforced by the approval service

- **Status:** accepted
- **Source of truth:** SPEC-REVIEW F8; `openspec/specs/human-approval/spec.md`; `services/approval/app.py` consume()

## Context

Flow C claimed a 'single-use' CIBA token, but CIBA returns an ordinary access token; nothing in Keycloak makes it single-use. Single-use requires replay tracking at the resource server, which appeared in no component's scope.

## Decision

The approval service issues a `<ref>.<secret>` action token (invalid until the ref is CIBA-approved) and is its sole introspector. Before the action runs, the tools-API calls `consume`, which verifies the payload hash and **atomically consumes** the reference (single-use); replay is refused (409). Falls out of ADR-0005 nearly for free.

## Alternatives considered

- B — soften the claim to 'short-TTL, single-action-scoped': honest, weaker.
- C — a JTI replay cache at the resource server: equivalent to A with more moving parts.

## Consequences

The single-use property is real and testable (`test_human_approval`, `test_reactive_approval`). Enforced in code — a trusted-code assumption (attack tree 3).

