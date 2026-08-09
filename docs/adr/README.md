# Architecture Decision Records

The stable, readable index of Prokura's material architectural decisions. These ADRs
are **derived from OpenSpec** (proposals, design docs, specs) and `SPEC-REVIEW.md` —
the OpenSpec artifacts remain the working **source of truth**, and every ADR cites
where its decision actually lives (ADR-0021). This corpus makes no decisions; it
records ones already made. Format: [`0000-template.md`](./0000-template.md).

## Index

| # | Title | Status | Source |
|---|-------|--------|--------|
| [0001](./0001-can-use-via-direct-assignment-a-write-time-invariant.md) | can_use via direct assignment + a write-time invariant | accepted | F1 |
| [0002](./0002-each-resource-server-is-its-own-token-audience.md) | Each resource server is its own token audience | accepted | F2 |
| [0003](./0003-honest-ttl-keycloak-tokens-900s-provider-re-issuance-interva.md) | Honest TTL — Keycloak tokens ≤900s; provider re-issuance interval ≤900s | accepted | F3 |
| [0004](./0004-github-app-not-oauth-app-a-provider-capability-manifest.md) | GitHub App (not OAuth app) + a provider-capability manifest | accepted | F4 |
| [0005](./0005-structured-approval-payload-out-of-band-reference-in-band-tr.md) | Structured approval payload out-of-band; reference in-band; trusted rendering | accepted | F5 |
| [0006](./0006-keycloak-s-built-in-ciba-http-channel-no-custom-java-spi.md) | Keycloak's built-in CIBA HTTP channel — no custom Java SPI | accepted | F6 |
| [0007](./0007-ntfy-is-notify-only-decisions-only-through-the-authenticated.md) | ntfy is notify-only; decisions only through the authenticated UI | accepted | F7 |
| [0008](./0008-single-use-action-token-enforced-by-the-approval-service.md) | Single-use action token enforced by the approval service | accepted | F8 |
| [0009](./0009-grant-acquisition-builds-on-keycloak-brokering-not-a-paralle.md) | Grant acquisition builds on Keycloak brokering, not a parallel OAuth flow | accepted | F9 |
| [0010](./0010-prokura-is-a-reference-architecture-not-a-production-platfor.md) | Prokura is a reference architecture, not a production platform | accepted | Q1 |
| [0011](./0011-keycloak-account-linking-for-acquisition-the-broker-owns-lif.md) | Keycloak account-linking for acquisition; the broker owns lifecycle | accepted | Q2 |
| [0012](./0012-per-agent-consent-screen-writes-the-can-use-tuple.md) | Per-agent consent screen writes the can_use tuple | accepted | Q3 |
| [0013](./0013-mcp-server-as-the-headline-demo-keycloak-as-the-mcp-authoriz.md) | MCP server as the headline demo (Keycloak as the MCP authorization server) | accepted | Q4 |
| [0014](./0014-python-for-v0-typescript-for-v1.md) | Python for v0, TypeScript for v1 | accepted | Q5 |
| [0015](./0015-mailpit-sink-for-the-gated-send-drive-shaped-acls-for-rag.md) | Mailpit sink for the gated send; Drive-shaped ACLs for RAG | accepted | Q6 |
| [0016](./0016-build-a-minimal-broker-credit-prior-art-track-xaa-id-jag-on-.md) | Build a minimal broker, credit prior art; track XAA/ID-JAG on the roadmap | accepted | Q7 |
| [0017](./0017-every-service-is-born-instrumented-telemetry-is-fire-and-for.md) | Every service is born instrumented; telemetry is fire-and-forget | accepted | observability |
| [0018](./0018-the-approval-trigger-lives-on-the-resource-server-reactive-s.md) | The approval trigger lives on the resource server (reactive step-up) | accepted | M4 |
| [0019](./0019-pgvector-in-the-existing-postgres-no-new-vector-container.md) | pgvector in the existing Postgres — no new vector container | accepted | M5 |
| [0020](./0020-a-local-offline-deterministic-embedder-for-rag-demo-grade.md) | A local, offline, deterministic embedder for RAG (demo-grade) | accepted | M5 |
| [0021](./0021-adrs-are-derived-from-openspec-the-specs-remain-the-source-o.md) | ADRs are derived from OpenSpec; the specs remain the source of truth | accepted | this change |
| [0022](./0022-the-approval-service-owns-the-ciba-ceremony-server-initiated.md) | The approval service owns the CIBA ceremony (server-initiated) | accepted | close-correct-party-gaps (M7) |

## Supersession chains

- **ADR-0001** supersedes the original `SPEC.md` §5 `can_use` intersection construct
  (`[agent] and operator from can_use`), which OpenFGA rejects.
- **ADR-0004** supersedes the original `SPEC.md` Flow B refresh-loop assumption that
  every provider (incl. classic GitHub OAuth apps) issues a refresh token.
- **ADR-0018** refines **ADR-0005** and **ADR-0008**: the approval *trigger* moved from
  agent-initiated (M3) to resource-server reactive step-up (M4); the hash-binding and
  single-use controls are unchanged.

## Decision inventory (completeness)

Every SPEC-REVIEW finding/decision and every listed locked choice maps to exactly one
accepted ADR or to a reasoned exclusion. Nothing is silently missing.

| Decision | Disposition |
|----------|-------------|
| F1–F9 | ADR-0001 … ADR-0009 (one each) |
| Q1–Q7 | ADR-0010 … ADR-0016 (one each) |
| Locked: sole-writer / `operator==owner` | recorded in ADR-0001 |
| Locked: broker's own token audience | recorded in ADR-0002 |
| Locked: TTL honesty / re-issuance interval | recorded in ADR-0003 |
| Locked: GitHub App vs OAuth app | recorded in ADR-0004 |
| Locked: ntfy notify-only | recorded in ADR-0007 |
| Locked: broker-brokered grants vs broker-run OAuth | recorded in ADR-0011 |
| Locked: Mailpit demo sink | recorded in ADR-0015 |
| Locked: MCP-first vs LangChain | recorded in ADR-0013 |
| Locked: Python-v0 / TS-v1 | recorded in ADR-0014 |
| Locked: born-instrumented observability | ADR-0017 |
| Locked: reactive step-up (M4) | ADR-0018 |
| Locked: server-initiated CIBA (M7) | ADR-0022 |
| Locked: pgvector-in-Postgres (M5) | ADR-0019 |
| Locked: offline embedder (M5) | ADR-0020 |
| ADR method (this change) | ADR-0021 |
| **Excluded** — security-baseline invariants | Not per-invariant ADRs: captured as verifiable requirements in [`openspec/specs/security-baseline/spec.md`](../../openspec/specs/security-baseline/spec.md) and verified in [`../security-review.md`](../security-review.md). The *decisions* they rest on (F1/F2/F5/F7/F8) already have ADRs. |
| **Excluded** — threat-model residual acceptances | Not decisions to record as ADRs: captured in the residual-risk register of [`../threat-model.md`](../threat-model.md). |
| **Excluded** — project rename (AgentGate → Prokura) | Naming, not an architectural decision; noted in ADR-0016. |
| **Open** (never settled) | None. No inventoried decision lacked a real resolution; no `accepted` ADR papers over an unsettled decision. |
