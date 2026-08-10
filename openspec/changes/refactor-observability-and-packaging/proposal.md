# Proposal: refactor-observability-and-packaging

## Why

Three things have accreted that make the reference harder to read than it should be, and
one honesty gap in what we ship. (1) **Traces aren't legible as a flow:** the synchronous
spine is already one Tempo trace, but you can't *find* "a Flow C trace" (no flow label,
buried under health-check noise), failed steps render green (no span status), the decisions
live only in logs (no span events), and the async ceremony legs are separate traces — so
"show me what this flow did end to end" isn't one click. (2) **The bespoke console
(`services/console`, :8095) reimplements Grafana/Tempo** as a branded skin — its own
docstring calls it "the headline demo view; Grafana stays for power-user drill-down." It is
maintenance surface that duplicates a better tool and drifts. (3) **`telemetry.py` is
copy-pasted across six services**, so a fix (like the M9 metrics meter) lands in one and not
the others. (4) **The compose file blurs what Prokura *is*:** the MCP server, tools-api, and
RAG retriever are *toy resource servers that prove the chain* — not Prokura — yet they sit
beside the trusted surfaces as if co-equal. Finally, the walkthroughs still lean on hand-drawn
recreations and old-console visuals; now that real screenshots are reliable, they should show
the real thing, everywhere it can be shown, without squishing on mobile.

## What Changes

- **Legible, flow-scoped traces.** One shared telemetry module gives every service: a
  `prokura.flow` (A/B/C/D) + `user`/`agent`/`decision` attribute on the flow's **root span**;
  `set_status(ERROR, reason)` on every deny/refusal path; the domain decisions
  (`issued`/`denied_*`/`approved`/`consumed`/`revoked`/`linked`) as **span events**; and the
  async ceremony legs (CIBA register → delegate → decide → complete; FastAPI background tasks)
  **linked** into one navigable trace. Result: search Tempo `{ prokura.flow = "C" }` → land on
  one clean end-to-end trace whose waterfall reads as the story, red where it was denied.
- **De-duplicated telemetry.** Extract the six copied `telemetry.py` into one shared module
  (`sdk/`-installed, like `prokura-py`): `setup(app, service)`, `tracer()`,
  `record_decision(span, …)`, and the metrics. Standardize trace↔log correlation on the
  **native OTel trace context** (Grafana derived field on `trace_id`) and keep the domain
  ref as an attribute; drop the redundant hand-copied `prokura.correlation_id` where it only
  duplicates the trace id.
- **Decommission the bespoke console.** Remove `services/console`, its compose service, its
  smoke test, and every doc/walkthrough reference. The observability surface is **Grafana +
  Tempo + Loki** (the provisioned dashboard + Explore), which already does the trace waterfall,
  the service graph, and the trace→logs jump natively and better.
- **Three-tier compose via profiles.** Group services as **prokura** (token-broker, approval,
  authority), **infra** (keycloak, openfga, openbao, postgres, ntfy, lgtm), and **test/demo**
  (mcp, tools-api, rag, acme realm, mailpit, spikes). A bare `docker compose up` brings
  prokura + infra (the product); `docker compose --profile demo up` adds the toy resource
  servers to run the full chain and the smoke suite. Makes "what is Prokura vs what proves it"
  legible in the one file everyone reads first.
- **Walkthrough visual rework.** Every UI screen is a **real screenshot**; wherever a
  walkthrough shows telemetry, it uses **real Grafana/Tempo/Loki screenshots** (replacing the
  bespoke-console shots and the hand-drawn `.wf` trace recreations). `.term` blocks remain only
  for genuine CLI/API text (their natural form). Wide content scrolls inside its own container
  so **nothing squishes on mobile**. Re-audit every walkthrough for glossed-over steps — if we
  do something and it can be shown, show it.
- **Surface OpenBao and the authority console in the main guided walkthrough.** The main tour
  (`docs/walkthroughs/index.html`) is the headline page everyone lands on, yet it glosses two
  things it currently only *asserts in text* — where the durable credential lives, and the
  principal's own view of who acts for them. Add, inline in the guided tour: (1) a **real
  OpenBao UI screenshot** at the moment the vault is used (`secret/grants/alice/acme`, values
  masked), so "the refresh credential never leaves OpenBao" is *shown*, not just claimed — these
  visuals exist today only in the `brokering.html`/`claude-code.html` deep-dives; and (2) a
  **dedicated guided-tour beat for the authority console** — the principal's own "my agents"
  register (who acts for you, each agent's consented grants, revoke in one click), shown with a
  **real screenshot** as a first-class stage in the narrative, not a bottom-of-page flowcard
  link. The six current stages are all the *agent's* happy path; the authority console is the
  *human's control surface* and is a core Prokura trusted surface (this change's own positioning:
  Prokura = the trusted surfaces), so the showcase page must actually **show what the product
  does for the principal**, not defer it to a sub-page. Both reuse existing surfaces (no new
  feature) and follow the same real-screenshot, mobile-safe rules.

## Capabilities

### Modified Capabilities

- `observability`: traces become **legible and flow-scoped** (flow tag on root spans, span
  status on denials, decisions as span events, async legs linked) and **trace↔log correlation
  standardizes on native trace context via Grafana**; the **bespoke-console requirement is
  removed** (decommissioned) and the observability surface is Grafana/Tempo/Loki; the pipeline
  smoke test targets Grafana/Tempo/Loki rather than the console.

## Impact

- Removed: `services/console/` (service + Dockerfile + index.html), its `docker-compose.yml`
  service, `tests/smoke/test_console.py`, and console references in docs/walkthroughs (esp.
  `docs/walkthroughs/postmortem.html`, which is console-centric → re-based on Grafana/Tempo).
- New: `sdk/prokura-telemetry/` (or `sdk/prokura-py/prokura/telemetry.py`) shared module;
  each service imports it instead of a local copy. Root-span flow tagging at each entrypoint
  (broker `/v1/tokens`, approval `/register`, mcp tools, rag, authority) + error-status/events.
- Modified: `docker-compose.yml` (3-tier profiles), all six `services/*/telemetry.py` (→ shared
  module), the deny/refusal paths across services (span status + events), Grafana datasource
  provisioning (Tempo→Loki derived field on trace_id), the LGTM dashboard (flow-scoped trace
  links; drop console-specific bits).
- Tests: `test_revocation`/`test_telemetry` etc. keep passing; add a smoke assertion that a
  driven flow produces a `prokura.flow`-tagged trace with a red span on a denied leg, and that
  a bare `docker compose config` (no profile) excludes the toy resource servers.
- Docs: walkthrough visual rework (real screenshots incl. telemetry, mobile-safe, no glossing);
  the main guided walkthrough (`index.html`) additionally shows the **OpenBao UI** (vault-use
  moment, masked) and the **authority console** ("my agents") inline, not just as text/links;
  architecture positioning note — **Prokura = the trusted surfaces; mcp/tools-api/rag are
  example resource servers that demonstrate it**; blog spot-check (likely fine) for mobile squish.
- Not a milestone; a cleanliness/clarity change. New ADR: decommission the bespoke console in
  favour of Grafana/Tempo/Loki + flow-scoped legible traces.

## Non-Goals

- Tail-based sampling / production observability posture (always-on stays for the demo).
- Rewriting the Grafana dashboard from scratch (enrich it: flow trace links; keep what works).
- Changing any authorization behavior — this is observability, packaging, and docs only.
- Re-recording blogs wholesale (they use real screenshots already; only fix mobile squish if found).
