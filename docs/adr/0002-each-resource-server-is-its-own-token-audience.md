# ADR-0002: Each resource server is its own token audience

- **Status:** accepted
- **Source of truth:** SPEC-REVIEW F2; `openspec/specs/identity-delegation/spec.md`; `services/*/validation.py`
- **Also records the locked choice:** Broker's own token audience (F2).

## Context

Flow A exchanged the user token to `aud=agent-tools-api`, then Flow B presented that same token to the broker — a broker accepting a token addressed to a different resource is the confused-deputy shape §11 exists to prevent.

## Decision

Agents perform an RFC 8693 exchange to `aud=token-broker`, and the broker **rejects any token whose `aud` isn't itself**. Extended through M4/M5: every resource server (tools-api `aud=agent-tools-api`, mcp `aud=mcp-server`, rag `aud=rag-server`) validates its own audience and never forwards an inbound token — each hop re-exchanges.

## Alternatives considered

- B — one multi-audience token: fewer round trips, wider blast radius per token.
- C — fold the broker into Keycloak as a custom grant (Auth0's shape): purest, but a substantial Java extension §11 rejected.

## Consequences

Two exchanges per flow, but every token is honest about its addressee; the F2 defense is testable per service. `docs/architecture.md` notes C as the 'what Auth0 does' comparison.

