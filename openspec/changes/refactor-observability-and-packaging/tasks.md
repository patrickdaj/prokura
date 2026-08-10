# Tasks: refactor-observability-and-packaging

## 1. Spike — prove the trace-legibility approach against the live stack

- [ ] 1.1 On one flow (broker hand-out), stamp the root span with `prokura.flow`/`user`/`agent`
      and confirm `{ prokura.flow = "B" }` in Tempo returns exactly that end-to-end trace
      (health-check noise excluded)
- [ ] 1.2 Set `span.set_status(ERROR, reason)` + a `denied` event on a deny path (e.g.
      `not_consented`) and confirm the span renders **red** with the reason in Grafana
- [ ] 1.3 Add a Tempo→Loki **derived field** on the trace id in datasource provisioning and
      confirm the one-click trace→logs jump works in Grafana Explore
- [ ] 1.4 Prove a span **link** joins an async leg (a background task or the CIBA delegate leg)
      back to its originating span, navigable in Grafana; record findings in the design doc

## 2. Shared telemetry module

- [ ] 2.1 Extract `sdk/prokura-telemetry/` (`setup`, `tracer`, `current_trace_id`,
      `record_decision(span, code, *, deny=False, **attrs)`, metrics helpers) from the six copies
- [ ] 2.2 Switch each service to a repo-root build context + `pip install ./sdk/prokura-telemetry`;
      add `.dockerignore` (exclude .git, docs, tests, spike, sibling service data)
- [ ] 2.3 Replace `from telemetry import …` in all six services with the shared module; delete
      the local `services/*/telemetry.py`

## 3. Legible, flow-scoped traces

- [ ] 3.1 Flow tag on the root span at each entrypoint: broker `/v1/tokens`, approval `/register`,
      each MCP tool, rag `/search`, authority `/api/*` (+ `prokura.decision` on completion)
- [ ] 3.2 `record_decision(..., deny=True)` on every refusal path (wrong audience, no grant,
      scope, not_consented, revoked, consent_refused, invalid token, wrong subject, expired)
- [ ] 3.3 Domain decisions (issued/approved/consumed/revoked/linked/denied_*) emitted as span
      **events** alongside the audit line
- [ ] 3.4 Link the CIBA ceremony legs (register → delegate → decide → complete) + re-attach
      context in the FastAPI background task; persist the originating span context on the row
- [ ] 3.5 Drop the redundant `prokura.correlation_id` (== trace id) from code + audit lines;
      keep the domain ref as an attribute

## 4. Grafana as the observability surface

- [ ] 4.1 Datasource provisioning: Tempo→Loki derived field on the trace id (the trace→logs jump)
- [ ] 4.2 Enrich the delegation-chain dashboard: per-flow trace links/panels; keep the
      time-to-stop panel; verify it renders (visually, not just the API)

## 5. Decommission the bespoke console

- [ ] 5.1 Remove `services/console/` (service, Dockerfile, index.html) and its `docker-compose.yml`
      service; remove `tests/smoke/test_console.py`
- [ ] 5.2 Remove every `:8095` / bespoke-console reference in docs; rebase
      `docs/walkthroughs/postmortem.html` on real Grafana/Tempo/Loki screenshots

## 6. Three-tier compose (profiles)

- [ ] 6.1 Group + comment `docker-compose.yml` as **prokura** (broker, approval, authority),
      **infra** (keycloak, openfga, openbao, postgres, ntfy, lgtm), **test/demo** (mcp, tools-api,
      rag, mailpit); put `profiles: ["demo"]` on the test/demo services
- [ ] 6.2 A bare `docker compose up` brings prokura + infra only; `--profile demo` adds the toy
      resource servers; update README quickstart, the `run` skill notes, and the smoke-test runner
- [ ] 6.3 Assert a bare `docker compose config` (no profile) contains no toy resource server;
      the smoke suite runs green under `--profile demo`

## 7. Walkthrough visual rework (real screenshots, mobile-safe, no glossing)

- [ ] 7.1 Re-audit every walkthrough page step-by-step: for each claim that has a visual, ensure
      a **real** screenshot is present (surfaces driven live via Playwright)
- [ ] 7.2 Replace bespoke-console shots and hand-drawn `.wf`/`.term`-trace recreations with **real
      Grafana/Tempo/Loki screenshots** (the driven flow's trace waterfall, correlated Loki lines,
      dashboard); keep `.term` only for genuine CLI/API text
- [ ] 7.3 Mobile: audit every wide element; wrap wide content in `overflow-x:auto` containers,
      images `max-width:100%` — verified at a narrow viewport; nothing squishes
- [ ] 7.4 Fill any glossed-over steps with real visuals; blog spot-check for mobile squish

## 8. Verify, document, close

- [ ] 8.1 **Acceptance:** drive a flow, search Tempo `{ prokura.flow = … }` → one end-to-end
      trace, red where denied, decisions inline, trace→logs jump works (screenshots)
- [ ] 8.2 Re-green the full smoke suite (`--profile demo`); telemetry smoke asserts a flow-tagged
      trace with a red denied span
- [ ] 8.3 Docs: architecture positioning — **Prokura = the trusted surfaces; mcp/tools-api/rag are
      example resource servers that demonstrate it**; observability section reflects Grafana-as-surface
- [ ] 8.4 New ADR: decommission the bespoke console in favour of Grafana/Tempo/Loki + flow-scoped
      legible traces (span tags/status/events/links); sync specs; archive
