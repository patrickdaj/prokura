# ADR-0016: Build a minimal broker, credit prior art; track XAA/ID-JAG on the roadmap

- **Status:** accepted
- **Source of truth:** SPEC-REVIEW Q7; `README.md`; `docs/architecture.md` Roadmap
- **Also records the locked choice:** Prior-art credit / naming.

## Context

Nango is an established OSS third-party OAuth token broker; Prokura's broker is a from-scratch subset. 'AgentGate' (the spec's original name) is collision-prone.

## Decision

Build a **minimal broker** and credit Nango explicitly (README + a comparison row) — the value is the *assembly* (delegation + CIBA + FGA + brokering under one identity model), not the broker in isolation. The project is named **Prokura** (the spec's 'AgentGate' was collision-prone). Track **Cross-App-Access (XAA)** / the ID-JAG grant on the v1 roadmap.

## Alternatives considered

- B — embed Nango: less code, a heavyweight dependency + license review.

## Consequences

Honest positioning. The XAA/ID-JAG note keeps the roadmap aligned with where the commercial ecosystem is heading.

