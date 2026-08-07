# ADR-0003: Honest TTL — Keycloak tokens ≤900s; provider re-issuance interval ≤900s

- **Status:** accepted
- **Source of truth:** SPEC-REVIEW F3; `openspec/specs/token-brokering/spec.md`; `docs/threat-model.md` TTL table
- **Also records the locked choice:** TTL honesty / re-issuance interval (F3).

## Context

§9's 'all agent-held tokens ≤15 min' is unenforceable for provider tokens: Google access tokens live ~1h, classic GitHub OAuth-app tokens never expire. `expires_in: 900` doesn't make a leaked provider token stop at 15 min.

## Decision

Restate honestly: Keycloak-issued delegated/broker-audience tokens are capped ≤900s (enforceable). The broker's provider-token **hand-out (re-issuance) interval** is ≤900s; residual provider-side validity is provider-controlled and documented in a per-provider TTL-honesty table, never claimed to be 15 min.

## Alternatives considered

- B — only support providers with short token lifetimes: shrinks the connector story to near zero.
- C — drop the rule for provider tokens entirely: loses a real bounded property for Keycloak tokens too.

## Consequences

The security claim is now true and defensible. The TTL table (`docs/threat-model.md`) states each provider's real residual validity.

