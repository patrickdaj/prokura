# ADR-0014: Python for v0, TypeScript for v1

- **Status:** accepted
- **Source of truth:** SPEC-REVIEW Q5; `sdk/prokura-py/`; `docs/architecture.md` Roadmap

## Context

Agent-app developers concentrate in TypeScript (Auth0 went JS-first), but the backend stack and idiomatic MCP servers here are Python.

## Decision

Ship the v0 SDK and services in **Python**; make a **TypeScript SDK an explicit v1** item — a decision, not a default.

## Alternatives considered

- B — TypeScript-first: better audience match, splits the stack for a solo build.
- C — both: not feasible in the v0 timeline.

## Consequences

The backend is already Python; MCP-in-Python is idiomatic. The TS SDK is tracked in the architecture Roadmap/v1 section.

