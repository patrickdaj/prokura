# Tasks: add-observability

## 1. LGTM receiver

- [x] 1.1 Pin a `grafana/otel-lgtm` image version and add it to compose: OTLP in (4317/4318), Grafana UI on host port 3001 (3000 is taken by another local stack), `deploy/lgtm/` mounted for provisioning
- [x] 1.2 Measure receiver startup time and memory; decide default-on vs `--profile obs` and record the decision + numbers in design.md (open question 3)

## 2. Component telemetry

- [x] 2.1 Verify the exact OTel tracing/metrics flag spellings against the pinned Keycloak 26.7.1 image (`kc.sh start-dev --help-all` / docs), enable them pointing at the receiver, and record the verified flags in design.md (open question 1)
- [x] 2.2 Enable realm event logging in `realm-export.json` (`eventsEnabled`, `adminEventsEnabled`, sensible expiration) and confirm events appear in the admin console event log
- [x] 2.3 Enable OpenFGA OTLP trace export + Prometheus metrics via compose env/flags; confirm check spans/metrics reach the receiver
- [x] 2.4 Enable the OpenBao file audit device (declarative `audit.hcl` — OpenBao 2.6 rejects runtime enable; init.sh verifies); confirmed secret reads/writes produce audit lines

## 3. Dashboard as code

- [x] 3.1 Create `deploy/lgtm/` provisioning: datasource config (as needed beyond the image defaults) and dashboard JSON auto-loaded at startup
- [x] 3.2 Build "delegation chain" dashboard v1 (7 panels: logins stat, identity-events rate, live realm-event log stream, request-rooted traces, req/s by endpoint, p95 latency, service graph — FGA activity visible via traces/service graph since FGA exports no scrapeable-into-LGTM metrics; Bao activity via audit file until M2) — convention noted in dashboard description

## 4. Telemetry smoke tests

- [x] 4.1 `tests/smoke/test_telemetry.py`: drive a login, then poll Tempo's API (bounded deadline) until a trace with Keycloak spans for that flow appears
- [x] 4.2 Loki test: realm LOGIN event queryable within seconds — resolved via Keycloak OTLP logs (`--telemetry-logs-*` + `success-level=info`), no tailer sidecar; recorded in design.md
- [x] 4.3 Grafana API test: the provisioned delegation-chain dashboard exists and datasources are healthy
- [x] 4.4 Receiver-outage check verified: receiver stopped → 8 core tests pass, 4 telemetry tests skip cleanly; documented in test module docstring

## 5. Wrap-up

- [x] 5.1 Clean-slate verification: `docker compose down -v && up`, full suite green — 16/16 in 57s (8 core + 4 telemetry + 4 spike)
- [x] 5.2 README: observability section — Grafana URL (:3001), what the dashboard shows, one-paragraph correlation-ID convention, receiver-down behavior
- [x] 5.3 Confirm all three design.md open questions carry recorded resolutions; state the M2/M3 definition-of-done inheritance (OTel instrumentation + traceparent propagation) in design.md's migration note
