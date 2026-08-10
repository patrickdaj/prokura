# ADR-0025: Decommission the bespoke console; Grafana/Tempo/Loki is the observability surface, and traces are flow-scoped and legible

- **Status:** accepted
- **Source of truth:** `openspec/changes/refactor-observability-and-packaging/`; `sdk/prokura-telemetry/`; `deploy/lgtm/`
- **Relationship:** Supersedes the "bespoke console is the headline view" requirement of the observability spec (the console shipped since M2 as `services/console`, `:8095`). Keeps every other observability invariant — fire-and-forget telemetry (ADR carried from M2), native `traceparent` correlation, the provisioned delegation-chain dashboard. Uses the M7 CIBA ceremony shape (ADR-0022) as the async legs it links; the authority console (ADR-0023) is unaffected — it is a *product* surface, not the observability console.

## Context

Three things made the reference harder to read than it should be. (1) The bespoke console (`services/console`, `:8095`) reimplemented the trace waterfall, service filtering, and the trace→logs jump that **Grafana + Tempo + Loki already provide natively and better**. Its own docstring called it "the headline demo view; Grafana stays for power-user drill-down" — it was duplicate, drift-prone maintenance surface. (2) The synchronous spine was already one Tempo trace, but it wasn't *legible as a flow*: you couldn't find "a Flow C trace" (no flow label, buried under health-check noise), failed steps rendered green (no span status), the domain decisions lived only in logs (no span events), and the CIBA ceremony legs were separate traces. (3) Trace↔log correlation carried a hand-copied `prokura.correlation_id` that only duplicated the native trace id — triple bookkeeping (span attr + log field + message string) of something OTel gives for free.

## Decision

**Grafana is the single observability surface**, and traces are made legible so the tool that already exists is enough:

- **Remove the bespoke console** — `services/console` (service, Dockerfile, `index.html`), its compose service, `tests/smoke/test_console.py`, and every `:8095` reference. The surface is **Grafana Explore → Tempo** for the flow waterfall, the provisioned **delegation-chain dashboard** for the overview, and the **Tempo→Loki derived field** for the trace→logs jump.
- **Flow-scoped, legible traces**, via one shared `prokura-telemetry` module (which also ends the six copied `telemetry.py`):
  - the flow's **root span** carries `prokura.flow` (A/B/C/D or `authority-console`) + `user`/`agent`, so `{ prokura.flow = "C" }` in Tempo returns exactly that end-to-end trace and health-check noise (no tag) is excluded;
  - every deny/refusal sets **span error status** with a machine-readable reason (a denied step is **red**, not green);
  - the domain decisions (`issued`/`approved`/`consumed`/`revoked`/`linked`/`denied_*`) are span **events**, so the trace narrates itself;
  - the CIBA ceremony's async legs (register → delegate → decide → complete), which cross Keycloak and a background task and so can't inherit `traceparent`, are joined by span **links** to the register origin.
- **Native trace↔log correlation.** Drop the hand-copied `prokura.correlation_id`; join on the native `trace_id` the logging handler attaches to every audit record, via a Grafana Tempo→Loki derived field pinned in repo-owned datasource provisioning. The domain ref (`apr-…`) still rides as a span attribute so a flow is also findable by domain id.

## Consequences

- One less surface to maintain; the curated demo narrative lives in the walkthroughs with **real** Grafana/Tempo/Loki screenshots instead of a duplicate app.
- A driven flow is one click from "what happened" (the flow-tagged, red-where-denied waterfall with decisions inline) to "the audit record of it" (the correlated Loki lines) — the thing the console hand-rolled, now native.
- **Alternative — keep a thin console that deep-links to Grafana:** rejected for this change (still a surface to maintain), but the door is open later if a branded one-screen demo is wanted; it would be a *new* thin artifact, not the current reimplementation.
- **Alternative — leave the correlation id / separate ceremony traces:** rejected as exactly the illegibility this change targets. Span links are less obvious than parent-child in Grafana, but that is honest — Keycloak cannot forward context — and the linked legs are one click from the origin trace.
