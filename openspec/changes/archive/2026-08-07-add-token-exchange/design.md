# Design: add-token-exchange (M1)

## Context

`identity-delegation` specifies RFC 8693 exchange + the F2-A broker-audience rule, but only login/TTL are implemented. M1 implements exchange and introduces the first real SDK code. The realm already flags `agent-app` with `standard.token.exchange.enabled` and defines `broker-audience`/`tools-audience` client scopes (M0), so much of the Keycloak side is wiring, not new infrastructure.

## Goals / Non-Goals

**Goals:** a working `exchange()` in `sdk/prokura-py`; realm token-exchange permissions per (client, audience), no wildcards; the F2-A audience defense demonstrated; the first cross-service delegated trace in the Console.

**Non-Goals:** no broker business logic (M2), no provider tokens, no consent. The `token-broker`/`agent-tools-api` clients stay bearer-only resources here — M1 only proves tokens are minted with the right `aud`.

## Decisions

1. **Standard token exchange, not the legacy V1 exchange.** Keycloak 26's standard token exchange (the `urn:ietf:params:oauth:grant-type:token-exchange` grant, `standard.token.exchange.enabled` on the client) is the supported path; verify the exact realm config against the pinned 26.7.1 image rather than from memory (M0 taught us telemetry flags churn; exchange config may too).
2. **Two explicit exchanges, not one multi-audience token (F2-A).** `exchange()` takes a single `audience` and callers make one call per audience. Keeps each token honest about its addressee; the broker (M2) rejects anything not addressed to it. A multi-audience convenience can come later if ergonomics demand.
3. **SDK is thin and dependency-light.** `httpx` + stdlib; no token cache, no disk writes (per the spec's no-persist requirement). The SDK targets the realm's token endpoint and is given client credentials by its caller/env — it does not embed secrets.
4. **Verify by driving, per project discipline.** An integration test performs login → exchange and decodes the returned token's claims; the delegated exchange is also confirmed visible as a linked trace in the Console before M1 is called done.

## Risks / Trade-offs

- [Standard-exchange realm config differs from memory on 26.7.1] → verify against the running image in task 1; adjust realm-export and re-import.
- [Exchange may require the target clients to be full (not bearer-only) or need audience mappers] → confirm during task 1; the M0 audience client scopes may need attaching as default/optional scopes on `agent-app` for the `aud` claim to appear.
- [SDK scope creep] → M1 ships `exchange()` only; other helpers are explicitly deferred to their milestones.

## Migration Plan

Additive. Realm re-import on `docker compose up` (dev). No rollback concerns. Sets up M2, which consumes the broker-audience token.

## Open Questions

- Exact standard-exchange permission model in Keycloak 26.7.1 (fine-grained admin permissions vs client setting) — resolve in task 1 against the image.
