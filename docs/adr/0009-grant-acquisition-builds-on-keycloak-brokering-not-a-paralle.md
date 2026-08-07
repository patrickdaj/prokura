# ADR-0009: Grant acquisition builds on Keycloak brokering, not a parallel OAuth flow

- **Status:** accepted
- **Source of truth:** SPEC-REVIEW F9; `openspec/specs/grant-acquisition/spec.md`

## Context

Keycloak with 'Store Tokens' already keeps upstream IdP tokens (`/broker/{alias}/token`) and, since 26.4, auto-refreshes them. The broker duplicated the acquisition half without acknowledging the overlap.

## Decision

Acquisition uses Keycloak identity brokering (see ADR-0011); the broker uniquely adds **leases, per-request scope-down policy, per-agent gating, and audit** on top. It does not re-implement OAuth acquisition.

## Alternatives considered

- Re-run acquisition in the broker (parallel OAuth): duplicates Keycloak, splits identity.

## Consequences

Less OAuth code; the broker earns its place by owning lifecycle, not acquisition. Same fork as Q2 (ADR-0011).

