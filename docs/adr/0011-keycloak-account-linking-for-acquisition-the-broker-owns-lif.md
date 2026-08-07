# ADR-0011: Keycloak account-linking for acquisition; the broker owns lifecycle

- **Status:** accepted
- **Source of truth:** SPEC-REVIEW Q2/F9; `openspec/specs/grant-acquisition/spec.md`; `deploy/keycloak/realm-export.json`
- **Also records the locked choice:** Broker-brokered grants vs broker-run OAuth (Q2).

## Context

The biggest architectural fork: run standalone OAuth flows the IdP never sees (splitting identity), or acquire through Keycloak.

## Decision

Use Keycloak identity providers with **Store Tokens** and **client-initiated account linking** (`kc_action=idp_link:<alias>`) to connect Google/GitHub to an existing account. The broker pulls the stored token via `/broker/{alias}/token`, imports the refresh token into OpenBao, and owns refresh/lease/scope-down. One identity, one consent surface.

## Alternatives considered

- A — broker-owned OAuth flows: max flexibility (incremental scopes), least Keycloak coupling, two consent surfaces, identity only correlated by broker bookkeeping.
- C — hybrid (login provider seeds via B, extras via A): two code paths, a v1 evolution.

## Consequences

Closest to Auth0's shape while the broker still earns its place (ADR-0009). Trade-off: scopes are configured statically per IdP, not incrementally per request.

