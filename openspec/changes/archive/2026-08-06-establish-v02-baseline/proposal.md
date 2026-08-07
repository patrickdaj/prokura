# Proposal: establish-v02-baseline

## Why

Prokura's design is complete — SPEC.md (Draft v0.1) was reviewed against Auth0 for AI Agents (SPEC-REVIEW.md, findings F1–F9 verified against official docs in Aug 2026), and all sixteen findings/decisions (F1–F9, Q1–Q7) were resolved in a recorded grilling session. That decision record currently lives across two narrative documents and a conversation; nothing is normative or testable yet. This change migrates the decided v0.2 design into OpenSpec capability specs and delivers the first implementable slice: the M0 skeleton (compose stack up, smoke tests green) including the week-one CIBA HTTP-channel spike that F6 identified as the plan's biggest de-risking opportunity.

## What Changes

- Establish six capability specs encoding the decided v0.2 design (this change's delta specs create them; they replace SPEC.md §4–§6 and §9 as the normative source).
- SPEC.md is superseded: normative content moves to specs; narrative content will later move to `docs/architecture.md` (out of scope here). SPEC-REVIEW.md remains as decision history feeding future ADRs.
- Implement M0: `docker-compose.yml` bringing up Keycloak (realm imported), OpenFGA (corrected model loaded — F1), OpenBao (dev mode), Postgres, self-hosted ntfy (F7), and Mailpit (Q6), with automated smoke tests.
- Spike Keycloak's built-in CIBA HTTP authentication channel (F6-A); outcome decides whether the Java SPI is deleted from the plan. Spike result recorded in the design doc.
- Rename: all artifacts use **Prokura** (Q7 resolved — name verified free on npm/PyPI; "AgentGate" was heavily collided).

## Capabilities

### New Capabilities

- `identity-delegation`: User authentication (OIDC) and delegated agent tokens via RFC 8693 token exchange — `sub` = user, `azp` = agent, downscoped, broker-audience exchange included (SPEC.md Flow A; F2-A).
- `grant-acquisition`: Third-party grant acquisition via Keycloak identity brokering + client-initiated account linking with Store Tokens; broker imports refresh tokens into OpenBao (Q2-B, F9).
- `token-brokering`: Broker-held provider-token lifecycle — leases, ≤15-min re-issuance, per-provider capability manifest, scope-down policy, audit (SPEC.md Flow B; F3-A, F4-A+C).
- `per-agent-consent`: Per-agent grant authorization — consent screen writes `can_use` FGA tuples; broker is sole tuple-writer enforcing operator == grant-owner (Q3-B, F1-A).
- `human-approval`: CIBA-based gated actions with structured approval payloads, reference-ID binding messages, trusted UI rendering, hash-verified execution, and consumed-action-ID replay rejection (SPEC.md Flow C; F5-A, F8-A, F6, F7).
- `rag-authorization`: FGA-filtered RAG retrieval evaluated as the end user, never the agent (SPEC.md Flow D; corpus plan per Q6: Drive-backed ACLs).

### Modified Capabilities

(None — no existing specs; this change establishes the baseline.)

## Impact

- New: `docker-compose.yml`, `deploy/keycloak/realm-export.json`, `deploy/openfga/model.fga`, `deploy/openbao/init.sh`, smoke-test suite, spike harness for the CIBA HTTP channel.
- Dependencies: Keycloak 26.4+, OpenFGA, OpenBao (dev mode), Postgres, ntfy (self-hosted), Mailpit.
- Documents: SPEC.md demoted from normative to historical once specs land; future changes (M1+) build on these capability specs.
- The MCP server capability (Q4, headline demo) is deliberately deferred to its own change after M0 — it depends on the skeleton existing.
