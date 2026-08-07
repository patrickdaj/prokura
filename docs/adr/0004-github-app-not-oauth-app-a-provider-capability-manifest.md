# ADR-0004: GitHub App (not OAuth app) + a provider-capability manifest

- **Status:** accepted
- **Source of truth:** SPEC-REVIEW F4; `openspec/specs/grant-acquisition/spec.md`; `services/token-broker/providers.py`
- **Relationship:** **Supersedes** the original SPEC.md Flow B OAuth-app refresh-loop assumption.
- **Also records the locked choice:** GitHub App vs OAuth app (F4).

## Context

Flow B assumed every provider issues a refresh token and supports scope narrowing. Classic GitHub OAuth apps issue non-expiring tokens with no refresh; GitHub doesn't support scope narrowing on refresh.

## Decision

Use a **GitHub App** with expiring user tokens (genuine refresh loop, ~8h bound). Add a provider manifest declaring `supports_refresh` / `supports_scope_narrowing`; Flow B acceptance is per-capability — cryptographic scope-down where supported (Google), policy enforcement (decline over-broad) where not (GitHub).

## Alternatives considered

- B — keep the OAuth app, store & re-hand the non-expiring token: simpler, visibly weaker.
- C — manifest only (adopted together with A).

## Consequences

Genuine refresh + bounded tokens match the security story; the manifest makes the second provider prove the abstraction. Slightly more demo setup (App vs OAuth app).

