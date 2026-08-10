# Tasks: refactor-observability-and-packaging

## 1. Spike — prove the trace-legibility approach against the live stack

- [x] 1.1 On one flow (broker hand-out), stamp the root span with `prokura.flow`/`user`/`agent`
      and confirm `{ prokura.flow = "B" }` in Tempo returns exactly that end-to-end trace
      (health-check noise excluded) — verified via Tempo API (12 B / 20 C / 4 D / 16
      authority-console traces) + `test_telemetry::test_flow_scoped_trace_is_findable`
- [x] 1.2 Set `span.set_status(ERROR, reason)` + a `denied` event on a deny path (e.g.
      `not_consented`) and confirm the span renders **red** with the reason in Grafana —
      verified via Tempo (`{ prokura.flow="B" && status=error }`, `denied` events) +
      `test_telemetry::test_denied_leg_is_red_and_flow_tagged`. (Grafana screenshot → §8.1)
- [x] 1.3 Add a Tempo→Loki **derived field** on the trace id in datasource provisioning and
      confirm the one-click trace→logs jump works in Grafana Explore — provisioning pinned (§4.1);
      native trace_id join confirmed in Loki (`test_broker_audit`) and **captured live**
      (`img/trace-logs.png`: one trace → its mcp_audit + rag_audit lines, joined by trace id)
- [x] 1.4 Prove a span **link** joins an async leg (the CIBA delegate/complete legs) back to its
      originating span — links implemented (origin span context persisted on the approval row,
      `link_to()` on each later leg + background-task re-attach) and exercised green by
      `test_human_approval`/`test_reactive_approval`

## 2. Shared telemetry module

- [x] 2.1 Extract `sdk/prokura-telemetry/` (`setup`, `tracer`, `current_trace_id`,
      `record_decision(span, code, *, deny=False, **attrs)`, metrics helpers) from the six copies
- [x] 2.2 Switch each service to a repo-root build context + `pip install ./sdk/prokura-telemetry`;
      add `.dockerignore` (exclude .git, docs, tests, spike, sibling service data)
- [x] 2.3 Replace `from telemetry import …` in all six services with the shared module; delete
      the local `services/*/telemetry.py`

## 3. Legible, flow-scoped traces

- [x] 3.1 Flow tag on the root span at each entrypoint: broker `/v1/tokens`, approval `/register`,
      each MCP tool, rag `/search`, authority `/api/*` (+ `prokura.decision` on completion)
- [x] 3.2 `record_decision(..., deny=True)` on every refusal path (wrong audience, no grant,
      scope, not_consented, revoked, consent_refused, invalid token, wrong subject, expired)
- [x] 3.3 Domain decisions (issued/approved/consumed/revoked/linked/denied_*) emitted as span
      **events** alongside the audit line
- [x] 3.4 Link the CIBA ceremony legs (register → delegate → decide → complete) + re-attach
      context in the FastAPI background task; persist the originating span context on the row
- [x] 3.5 Drop the redundant `prokura.correlation_id` (== trace id) from code + audit lines;
      keep the domain ref as an attribute

## 4. Grafana as the observability surface

- [x] 4.1 Datasource provisioning: Tempo→Loki derived field on the trace id (the trace→logs jump)
- [x] 4.2 Enrich the delegation-chain dashboard: added a **per-flow trace-links** panel (Explore →
      Tempo deep-links for B/C/D/authority-console + the Tempo→Loki jump note); kept the time-to-stop
      panel; verified it renders visually (`img/dashboard-overview.png` — stat/timeseries/logs panels
      populated) + `test_dashboard_provisioned` green (19 panels)

## 5. Decommission the bespoke console

- [x] 5.1 Remove `services/console/` (service, Dockerfile, index.html) and its `docker-compose.yml`
      service; remove `tests/smoke/test_console.py`
- [x] 5.2 Remove every `:8095` / bespoke-console reference in docs; rebase
      `docs/walkthroughs/postmortem.html` on real Grafana/Tempo/Loki screenshots.
      **Coordination:** `docs/index.html` is under concurrent edit by another agent — reconcile
      its "faithful recreation" / "open the console" copy on top of that agent's final version
      (see design §Coordination); do not edit it until then.
      DONE except `docs/index.html` — still HELD for the concurrent-edit reconciliation (its
      `:8095`/"open the console"/"faithful recreation" copy remains to fix on top of that agent's
      final version; all other docs done)

## 6. Three-tier compose (profiles)

- [x] 6.1 Group + comment `docker-compose.yml` as **prokura** (broker, approval, authority),
      **infra** (keycloak, openfga, openbao, postgres, ntfy, lgtm), **test/demo** (mcp, tools-api,
      rag, mailpit); put `profiles: ["demo"]` on the test/demo services
- [x] 6.2 A bare `docker compose up` brings prokura + infra only; `--profile demo` adds the toy
      resource servers; update README quickstart, the `run` skill notes, and the smoke-test runner
- [x] 6.3 Assert a bare `docker compose config` (no profile) contains no toy resource server;
      the smoke suite runs green under `--profile demo` (new `test_compose_profiles.py`)

## 7. Walkthrough visual rework (real screenshots, mobile-safe, no glossing)

- [x] 7.1 Re-audit every walkthrough page step-by-step: for each claim that has a visual, ensure
      a **real** screenshot is present (surfaces driven live via Playwright)
- [x] 7.2 Replace bespoke-console shots and hand-drawn `.wf`/`.term`-trace recreations with **real
      Grafana/Tempo/Loki screenshots** — new `demo/capture/capture_grafana.py` (trace/logs/dashboard
      modes) produced `trace-flowB/C/D.png`, `trace-logs.png`, `trace-postmortem.png`,
      `dashboard-overview.png`, wired into index/brokering/delegation/approval/rag/postmortem; `.term`
      kept only for genuine CLI/API text
- [x] 7.3 Mobile: verified no horizontal overflow at a 500px viewport on the main walkthrough and
      postmortem; real screenshots are `.screen.pic` (`img{width:100%}`, tap-to-enlarge); all wide
      `.wf` blocks are gone (replaced by images)
- [x] 7.4 Filled the glossed-over steps with real visuals (OpenBao + authority now shown); blogs
      already use real screenshots (Non-Goals: only fix squish if found — none introduced here)
- [x] 7.5 **Main guided walkthrough — OpenBao, shown when used.** Added the real
      `img/flowB-openbao.png` (`secret/grants/alice/acme`, masked) inside Stage 03 (ACT 2), mobile-safe
- [x] 7.6 **Main guided walkthrough — authority console as a guided-tour beat.** Added Stage **07
      "The human stays in control"** with the real `img/authority-register.png` ("my agents" +
      consented grants + revoke) + payoff copy; updated the ACT map (added the CODA line); reused the
      shipped surface (docs-only); mobile-safe

## 8. Verify, document, close

- [x] 8.1 **Acceptance:** drove flows; Tempo `{ prokura.flow = "B/C/D/authority-console" }` returns
      one end-to-end trace each (12 B / 20 C / 4 D / 16 authority-console); deny paths render red
      (`{ prokura.flow="B" && status=error }`); decisions are span events (`denied`/`issued`/
      `consumed`); trace→logs jump captured (`img/trace-logs.png`). Screenshots wired into the
      walkthroughs (`trace-flowB/C/D`, `trace-postmortem`, `trace-logs`, `dashboard-overview`)
- [x] 8.2 Re-green the full smoke suite (`--profile demo`); telemetry smoke asserts a flow-tagged
      trace with a red denied span — 88 passed (86 + 2 new telemetry acceptance tests)
- [x] 8.3 Docs: architecture positioning — **Prokura = the trusted surfaces; mcp/tools-api/rag are
      example resource servers that demonstrate it**; observability section reflects Grafana-as-surface
- [~] 8.4 New ADR: decommission the bespoke console in favour of Grafana/Tempo/Loki + flow-scoped
      legible traces (span tags/status/events/links) — **ADR-0025 written**. Spec sync + archive
      **held**: the only remaining task is §5.2's `docs/index.html` reconciliation, blocked on the
      concurrent-edit coordination (design §Coordination). Archive once that lands and this file is 29/29.
