# Proposal: add-observability

## Why

Prokura's whole value is *showing* how agentic identity works, but today the only realtime window into the stack is `docker compose logs -f`. The specs demand audit with correlation IDs (token-brokering), yet audit-as-a-table is read after the fact — nobody can watch a delegated action ripple through Keycloak → OpenFGA → OpenBao → approval as it happens. Every component we chose already speaks OpenTelemetry natively (Keycloak 26 tracing/metrics, OpenFGA OTLP export, OpenBao telemetry + audit device, FastAPI auto-instrumentation); we've simply never wired a receiver. Doing it now — before M1/M2 — means the token broker and approval service are *born* instrumented instead of retrofitted, and the "delegation chain as a live distributed trace" becomes a headline demo visual alongside MCP.

## What Changes

- Add a `grafana/otel-lgtm` service (Grafana + Tempo + Loki + Prometheus, single dev container) to the compose stack, with a pre-provisioned "delegation chain" dashboard.
- Turn on native telemetry in existing services: Keycloak tracing/metrics + realm event logging (`eventsEnabled`), OpenFGA OTLP trace/metric export, OpenBao telemetry stanza + file audit device (extends `deploy/openbao/init.sh`).
- Establish the correlation-ID convention (W3C `traceparent` propagation; the approval reference ID and audit correlation ID join to the trace) as a binding design constraint for all future Python services (M2 broker, M3 approval service).
- Amend the token-brokering audit requirement: audit events are additionally emitted to the telemetry pipeline in realtime (Loki-queryable), not only persisted to Postgres.
- Smoke tests prove the pipeline: traces from a login flow appear in Tempo; an audit-shaped event is queryable in Loki; Grafana serves the provisioned dashboard.

## Capabilities

### New Capabilities

- `observability`: Realtime telemetry for every cross-service flow — end-to-end trace propagation with correlation IDs, OTel export from all stack components, a bundled LGTM receiver with a provisioned delegation-chain dashboard, and realtime-queryable audit events.

### Modified Capabilities

- `token-brokering`: The "Issuance audit log" requirement gains a realtime-emission clause — every audit event (issuance and denial) is emitted to the telemetry pipeline as it occurs, carrying the same correlation ID as the persisted record, so the audit trail is watchable live, not only queryable after the fact.

## Impact

- `docker-compose.yml`: one new pinned service (`grafana/otel-lgtm`), OTel env/config flags on keycloak and openfga; Grafana UI port published.
- `deploy/keycloak/realm-export.json`: `eventsEnabled` (+ admin events) so realm events are observable.
- `deploy/openbao/init.sh`: enable the file audit device.
- New `deploy/grafana/` (or `deploy/lgtm/`): dashboard JSON + datasource provisioning.
- `tests/smoke/`: new telemetry smoke tests.
- Design constraint inherited by M2/M3 services (OTel instrumentation + traceparent propagation is now part of their definition of done); M1's exchange tests become the first real multi-service trace.
- No breaking changes; all additions are compose-local and dev-mode.
