# Design: establish-v02-baseline

## Context

SPEC.md (Draft v0.1) was reviewed against Auth0 for AI Agents; every capability claim was verified against official sources (Aug 2026), and all sixteen findings/decisions were resolved. The stack is Keycloak 26.4+ / OpenFGA / OpenBao / Postgres / FastAPI, docker-compose only, explicitly non-production. This change encodes the decided design as capability specs and implements M0: the compose skeleton plus the one experiment (CIBA HTTP channel spike) whose outcome reshapes later milestones.

## Goals / Non-Goals

**Goals:**
- Capability specs become the normative source, superseding SPEC.md §4–§6/§9.
- A `docker-compose up` skeleton: Keycloak (realm imported), OpenFGA (valid model loaded), OpenBao (dev mode), Postgres, self-hosted ntfy, Mailpit — with automated smoke tests.
- CIBA HTTP-channel spike answered with evidence: does the built-in channel deliver the delegation POST and accept the callback? Result recorded here (Open Questions → resolved).

**Non-Goals:**
- No broker business logic, no approval service/UI, no MCP server, no RAG pipeline (later changes: M1–M4).
- No production hardening, HA, or multi-tenancy (SPEC.md §2 non-goals stand).
- No SPEC.md narrative rewrite into docs/architecture.md yet (follow-up change alongside M5 polish).

## Decisions

1. **One change per milestone; this change = specs + M0.** The full capability specs land now (the design is finished and verified) while implementation arrives milestone-by-milestone. Alternative — one giant change implementing everything — rejected: no reviewable increments, and the no-deadline risk profile needs a demoable artifact per slice.
2. **Grant acquisition via Keycloak account linking, broker owns lifecycle (Q2-B/F9).** Keycloak 26.4+ stores *and* auto-refreshes linked-IdP tokens, so hand-rolling provider OAuth in the broker would duplicate the platform. The broker's earned scope is leases, per-agent consent, scope-down policy, audit. Alternative (broker-owned flows) rejected: two consent surfaces, identity correlated only by bookkeeping, Nango-shaped redundancy.
3. **FGA `can_use` as direct assignment + broker write-time invariant (F1-A/Q3-B).** OpenFGA cannot express the cross-object join "agent's operator == grant owner"; the invariant moves into the sole tuple-writer (broker). Per-agent consent is load-bearing because MCP DCR admits self-registered clients. Alternatives: two-check broker logic (loses per-agent granularity), Auth0-style no-FGA (loses the consent gate entirely).
4. **Broker gets its own token audience (F2-A).** Second RFC 8693 exchange for `aud=token-broker`; broker rejects other audiences. Folding the vault into Keycloak as a custom grant (Auth0's true shape) is documented as the ADR comparison point but rejected for v0: deep Java SPI in the least-hackable, highest-blast-radius location.
5. **Structured approval with reference-ID binding messages (F5-A/F8-A).** Keycloak's `binding_message` validation (`^[a-zA-Z0-9-._+/!?#]{1,50}$`) rejects free text anyway; the approval payload lives in the approval service, the UI renders only service-held data, and the resource server enforces hash match + consumed-ID single-use. This reproduces RAR's security properties without Keycloak internals (Keycloak has no RAR support as of mid-2026).
6. **Spike the built-in CIBA HTTP channel before writing any Java (F6-A).** Config flag: `--spi-ciba-auth-channel--ciba-http-auth-channel--http-authentication-channel-uri` (Keycloak 26+ double-dash form). Success deletes `extensions/keycloak-ciba-ntfy/` from the plan; failure falls back to the Java SPI with findings documented.
7. **Notifications are capability-free (F7-A+B).** Self-hosted ntfy with ACLs in compose; messages carry deep link + reference ID only; decisions happen solely in the Keycloak-session-gated UI. Web Push rejected for v0 (VAPID/service-worker cost, marginal gain).
8. **GitHub App, not OAuth app (F4-A+C).** Expiring user tokens give the refresh loop something real to refresh; the provider manifest (`supports_refresh`, `supports_scope_narrowing`) keeps acceptance criteria honest per provider.
9. **Mailpit for gated email; Drive-backed ACLs for RAG (Q6).** Zero Google-verification friction in the quickstart (Auth0 customers face the identical Google gauntlet — no commercial advantage lost); Google instead showcases real-world ACL mirroring in Flow D.

## Risks / Trade-offs

- [CIBA HTTP channel is lightly documented; spike may fail] → Java SPI fallback is scoped and budgeted; spike runs in M0, not M3, so the discovery is cheap.
- [Approval service joins the trusted computing base (can swap payloads if compromised)] → Threat model explicitly lists TCB = Keycloak + broker + approval service; payload hash recorded at registration narrows the tamper window; compose network isolates the service.
- [Broker as sole FGA tuple-writer is a single point of authorization truth] → Write-time invariant is unit-tested; threat model documents the trust; audit log records every tuple write.
- [Static per-IdP scopes (no incremental consent)] → Documented trade-off; matches the commercial reference product; per-agent consent provides the granularity story instead.
- [Keycloak version coupling (26.4+ features: MCP AS support, stored-token refresh, spi option format)] → Pin the compose image; record the minimum version in the realm README; CI smoke test runs against the pinned image.
- [No deadline → stall risk at the unglamorous middle] → Every change ships a demoable artifact; M0's is `docker-compose up` + green smoke tests + a spike verdict.

## Migration Plan

Greenfield repo; no rollback concerns. Sequence: specs land (this change) → M0 implementation → `openspec sync` promotes deltas to main specs → subsequent changes per milestone (M1 exchange, M2 broker, M3 approval, M4 RAG/MCP demo, M5 polish + SPEC.md retirement).

## Open Questions

(None — both resolved at M0 completion.)

## Spike Verdict (resolved, M0)

**The built-in CIBA HTTP channel works on Keycloak 26.7.1 — the Java SPI is deleted from the plan.** All four paths verified against the live stack (`spike/ciba-http-channel/test_spike.py`): delegation POST arrives at the external endpoint with `binding_message` and bearer token; SUCCEED via the callback yields a token on the CIBA poll; UNAUTHORIZED yields `access_denied`; undecided requests stay `authorization_pending`. M3 is now Python + configuration.

Integration facts the approval service must honor (discovered in the spike):
1. The delegation endpoint MUST return **HTTP 201** — Keycloak treats 200 as "unexpected response from authentication device" (503 to the initiating client).
2. The delegation JWT's issuer is validated at the callback — `KC_HOSTNAME` must be pinned (compose: `http://localhost:8180`, `KC_HOSTNAME_BACKCHANNEL_DYNAMIC=false`) so host-side and container-side callers see the same issuer.
3. Keycloak realm-import quirk: declaring `clientScopes` suppresses ALL built-in scopes — `basic` (sub mapper, `access.token.claim=true` required) and `profile` must be defined explicitly or `sub` silently vanishes from tokens.

Image pins (resolved): Keycloak 26.7.1, OpenFGA v1.18.3, OpenBao 2.6.1, ntfy v2.27.0, Mailpit v1.30.6, Postgres 17-alpine.
