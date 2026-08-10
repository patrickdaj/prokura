# Design: refactor-observability-and-packaging

## Context

The synchronous spine is already one Tempo trace (traceparent propagates via httpx
auto-instrumentation) — but it isn't *legible* as a flow, the bespoke console duplicates
Grafana, `telemetry.py` is copied six times, and the compose file presents toy resource
servers as if they were Prokura. This change makes traces readable end-to-end, deletes the
duplicate console, unifies telemetry into one module, tiers the compose file, and re-audits
the walkthroughs to show the real thing. Constraints carried throughout: telemetry stays
fire-and-forget (no service depends on the receiver); no authorization behavior changes;
"verified by looking" — if we do it and it can be shown, show it.

## Goals / Non-Goals

**Goals:** one-click "show me a Flow X trace end-to-end" (flow-tagged, red where denied,
decisions inline); one shared telemetry module; the bespoke console gone; a compose file that
says what Prokura is; walkthroughs that use real screenshots (incl. telemetry) and don't
squish on mobile.

**Non-Goals:** tail-sampling / production posture; a Grafana dashboard rewrite; any authz
change; re-recording blogs; full traceparent propagation *through* Keycloak's CIBA callback
(impossible — KC doesn't forward it; we use span links).

## Decisions

### D1 — One shared telemetry module, via a shared build context

Extract the six copied `telemetry.py` into a single installable package
`sdk/prokura-telemetry/` exposing `setup(app, service_name)`, `tracer()`,
`current_trace_id()`, `record_decision(span, decision, *, deny=False, **attrs)`, and the
metrics helpers. Each service imports it (`from prokura_telemetry import …`) and its local
`telemetry.py` is deleted. Because service images build from their own directory today
(`build: ./services/x`), the package isn't in their build context — so each service switches
to a **repo-root build context** (`build: { context: ., dockerfile: services/x/Dockerfile }`)
and `pip install ./sdk/prokura-telemetry`, with a `.dockerignore` to keep the context lean.

*Alternative — vendor a copy per service:* rejected; that is the current problem. *Alternative
— publish to an index:* overkill for a dev reference; a local path install is simplest.

### D2 — Flow-scoped, legible traces

- **Flow tag on the root span.** At each flow entrypoint (broker `/v1/tokens/{provider}`,
  approval `/register`, each MCP tool, rag `/search`, authority `/api/*`) the handler stamps
  the active (FastAPI server) span with `prokura.flow` (A/B/C/D or a surface name),
  `prokura.user`, `prokura.agent`, and — on completion — `prokura.decision`. Then
  `{ prokura.flow = "C" }` in Tempo lands on one clean end-to-end trace, and health-check
  noise never carries the tag.
- **Failures are red.** Every deny/refusal path calls `record_decision(span, code, deny=True)`,
  which sets `span.set_status(Status(ERROR, code))` and adds a `denied` span event with the
  reason. A denied consent / wrong audience / revoked hand-out now shows a red span in the
  waterfall, not green.
- **Decisions are span events.** The audit decisions (`issued`/`approved`/`consumed`/
  `revoked`/`linked`/`denied_*`) are emitted as span **events** (same attributes as the audit
  line) so the trace narrates itself — no log cross-reference needed to read the story.
- **Native trace↔log join.** Correlation standardizes on the OTel logging handler's
  `trace_id`/`span_id` (already attached to every log record) + a Grafana **Tempo→Loki derived
  field** on `trace_id`. The redundant hand-copied `prokura.correlation_id` (== the trace id)
  is dropped from code and audit lines where it only duplicates the trace id; the *domain* ref
  (`apr-…`) stays as an attribute for domain search. Dashboards/LogQL that grepped
  `correlation_id=` migrate to the trace-id derived field first.

*Alternative — keep `prokura.correlation_id`:* rejected as triple bookkeeping (span attr + log
field + message string) of something OTel gives natively.

### D3 — Link the async ceremony legs into one navigable trace

The CIBA ceremony is inherently multi-trace: register → Keycloak → a *separate* inbound
`/ciba/delegate`, then `/decide`, then a FastAPI **background** `_complete_ceremony`. Keycloak
doesn't forward traceparent, so parent-child continuity is impossible. Instead: persist the
register span's `{trace_id, span_id}` on the approval row, and every subsequent ceremony span
is created with an OTel **`Link`** to it (plus the ref as an attribute). The background task
additionally captures and re-attaches the request context (`context.attach`) so its httpx
spans aren't orphaned. Result: from the register trace, Grafana shows the linked delegate/
decide/complete spans — the whole ceremony is navigable as one story even though it spans
three transport hops.

*Alternative — leave them as separate traces:* rejected; "one approval, three traces" is
exactly the illegibility this change targets.

### D4 — Decommission the bespoke console; Grafana/Tempo/Loki is the surface

Remove `services/console` (service, Dockerfile, `index.html`), its compose service, and
`tests/smoke/test_console.py`. The observability surface becomes Grafana: **Explore → Tempo**
for the flow waterfall, the provisioned **delegation-chain dashboard** for the overview (it
already has the time-to-stop panel), and the **Tempo→Loki derived field** (configured in
datasource provisioning) for the one-click trace→logs jump the console used to hand-roll.
`docs/walkthroughs/postmortem.html` (console-centric) is re-based on real Grafana/Tempo/Loki
screenshots; every `:8095` reference is removed.

*Alternative — keep a thin console that deep-links to Grafana:* considered; rejected for this
change (still a surface to maintain), but the door is open later if a branded one-screen demo
is wanted — it would be a *new* thin artifact, not the current reimplementation.

### D5 — Three-tier compose via profiles

`docker-compose.yml` groups services and comments the three tiers. **prokura** (token-broker,
approval, authority) and **infra** (keycloak, openfga, openbao, postgres, ntfy, lgtm) carry no
profile — a bare `docker compose up` brings the product. **test/demo** (mcp, tools-api, rag,
mailpit, ciba-spike) get `profiles: ["demo"]`; `docker compose --profile demo up` adds them to
run the full chain and the smoke suite. The acme *realm* still imports into Keycloak (inert
data, harmless unwired); the tiering is about the toy *services*. README/quickstart and the
smoke-test runner are updated to `--profile demo`.

*Alternative — two files (base + override):* the user chose profiles-in-one-file; it keeps the
single file everyone reads and makes the tiers visible inline.

### D6 — Walkthrough visual rework: real screenshots, mobile-safe, nothing glossed

Real screenshots for every surface (driven live via Playwright) and for every telemetry view
(open the driven flow's trace in Grafana/Tempo, the correlated Loki lines, the dashboard — and
screenshot those), replacing the bespoke-console shots and the hand-drawn `.wf`/`.term`-trace
recreations. `.term` blocks remain only for genuine CLI/API text. Mobile: audit every wide
element; wide content lives in an `overflow-x:auto` container (extend `walkthrough.css` where a
block still squishes) and images are `max-width:100%`. Completeness: walk each page step-by-step
and, for any claim that has a visual, ensure the visual is present and real — fill the gaps.

## Risks / Trade-offs

- [Shared build context enlarges each image's context] → a `.dockerignore` (exclude
  `.git`, `docs`, `tests`, `spike`, other services' data) keeps builds fast.
- [Dropping `prokura.correlation_id` breaks a dashboard/LogQL that greps it] → migrate the
  Tempo→Loki join to the native trace-id derived field *first*, then remove the field; the
  domain ref stays searchable.
- [Span links are less obvious than parent-child in Grafana] → acceptable and honest (KC can't
  forward context); the register trace's linked spans are one click away and documented.
- [Decommissioning the console loses the branded demo screen] → Grafana Explore + the
  provisioned dashboard cover the function; the walkthroughs carry the *curated* narrative with
  real screenshots, which is the demo artifact that mattered.
- [`--profile demo` is an extra flag for the smoke suite] → documented in one place; CI/`run`
  scripts updated; the payoff is a compose file that tells the truth about what Prokura is.

## Migration Plan

Additive-then-subtractive, clean-slate friendly: (1) land the shared telemetry module + flow
tags/status/events/links behind the existing pipeline; (2) add the Grafana Tempo→Loki derived
field and verify the trace→logs jump; (3) remove the console (service, compose, test, docs
refs) once Grafana covers it; (4) tier the compose file and update README/`run`; (5) rework the
walkthrough visuals. Rollback = git revert + clean compose up. No authorization or data-model
change, so no runtime migration.

## Coordination

`docs/index.html` (the site landing) is under **concurrent edit by another agent**. Do NOT
touch it until that work lands; then integrate this change's landing-page items **on top of
the final version**, specifically: replace the "faithful recreation of each screen" language
and remove "open the console" / any `:8095` reference (console decom, task 5.2), and confirm
the walkthrough/telemetry links still point at the real-screenshot pages (task 7.x). Re-check
its mobile layout after merge (task 7.3). Held pending that agent's completion.

## Open Questions

- Shared telemetry home: a standalone `sdk/prokura-telemetry/` package vs a `telemetry`
  submodule of the existing `prokura` SDK. Default: standalone package (services shouldn't pull
  the SDK's agent-side deps). Confirm during apply.
- Whether to keep `ciba-spike` in the `demo` profile or a separate `spike` profile (it already
  uses `profiles: [spike]`). Default: leave its `spike` profile as-is; it isn't part of `demo`.
