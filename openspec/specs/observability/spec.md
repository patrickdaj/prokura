# observability

## Purpose

Realtime telemetry for every cross-service flow: trace propagation with correlation IDs, native OTel export from all stack components, a bundled LGTM receiver with a provisioned delegation-chain dashboard, and audit events watchable live. Rationale: the project's product is *explaining* agentic identity — a delegation chain rendered as a live distributed trace is documentation.

## Requirements

### Requirement: End-to-end trace propagation with correlation IDs
Every cross-service flow SHALL propagate W3C Trace Context (`traceparent`) across all participating services. Domain correlation identifiers — the token-brokering audit correlation ID and the human-approval reference ID — SHALL be attached to the active trace (span attributes), so a single trace links Keycloak, OpenFGA, OpenBao, broker, and approval activity for one logical action. All Prokura-built services (broker, approval, demo APIs) MUST be OTel-instrumented from their first commit; this is part of their definition of done.

#### Scenario: One flow, one trace
- **WHEN** an agent completes a flow that touches more than one service (e.g., token exchange followed by a broker call)
- **THEN** a single trace exists containing spans from each participating service, joined by the propagated trace context

#### Scenario: Domain IDs joined to the trace
- **WHEN** a broker audit event or an approval reference ID is created inside a traced flow
- **THEN** the trace's spans carry that identifier as an attribute, and searching Tempo by it finds the trace

### Requirement: Stack components export telemetry
Keycloak and OpenFGA SHALL export their native telemetry to the bundled collector: Keycloak with tracing and metrics enabled, OpenFGA with OTLP trace export enabled. OpenBao has no trace export (its telemetry surface is metrics sinks and the audit device only — verified against OpenBao 2.6 docs); it SHALL have the file audit device enabled, and its operations become trace-visible via caller-side spans once instrumented services (M2 broker) call it. Keycloak realm event logging (`eventsEnabled`, including admin events) SHALL be on so identity events are observable.

#### Scenario: Login produces a Keycloak trace
- **WHEN** a user completes an OIDC login against the realm
- **THEN** spans from Keycloak for that request are queryable in the trace backend

#### Scenario: FGA check visible
- **WHEN** an OpenFGA check is executed
- **THEN** a corresponding span or metric increment is observable in the receiver

#### Scenario: Bao access is audited
- **WHEN** any OpenBao secret path is read or written
- **THEN** the access appears in OpenBao's audit device output

### Requirement: Bundled receiver with provisioned dashboard
The compose stack SHALL include a single dev-mode LGTM receiver (Grafana + Tempo + Loki + Prometheus) with datasources pre-provisioned and a "delegation chain" dashboard bundled from the repo — no manual Grafana setup. The provisioned dashboard MUST actually render (verified visually, not only via the dashboards API — exotic panel types such as `traces`/`nodegraph` can crash Grafana's render silently). The stack MUST remain functional if the receiver is down (telemetry is fire-and-forget; no service depends on it).

#### Scenario: Zero-setup dashboard
- **WHEN** the stack comes up from a clean clone and a user opens Grafana
- **THEN** the delegation-chain dashboard exists and its panels render against pre-provisioned datasources without any manual configuration

#### Scenario: Telemetry outage is non-fatal
- **WHEN** the receiver container is stopped
- **THEN** logins, FGA checks, and Bao operations continue to succeed

### Requirement: Bespoke console is the headline view
The stack SHALL serve a bespoke, self-contained observability console (its own container) as the primary human-facing view, distinct from Grafana (which remains for ad-hoc drill-down). The console SHALL be interactive — not a static readout: it presents the delegation chain as clickable service filters and a live trace stream where selecting a trace renders its span waterfall. It queries Prometheus, Loki, and Tempo through Grafana's datasource proxy (same-origin, no CORS). It MUST surface more than one service's telemetry — at minimum Keycloak and OpenFGA traces — so the cross-service story is visible, not just Keycloak logs.

#### Scenario: Interactive trace drill-down
- **WHEN** a user selects a trace in the console's stream
- **THEN** the span waterfall for that trace renders, showing per-span service, name, and duration

#### Scenario: Cross-service visibility
- **WHEN** the user filters the trace stream to OpenFGA
- **THEN** OpenFGA authorization traces appear (health-check noise excluded), decomposing into the ReBAC resolution spans — demonstrating visibility beyond Keycloak

### Requirement: Audit events are watchable in realtime
Audit-relevant events (broker issuances/denials once the broker exists; Keycloak realm events; Bao audit lines) SHALL be queryable in the log backend (Loki) within seconds of occurring, carrying their correlation IDs, so an operator can watch the audit trail live rather than only querying it after the fact.

#### Scenario: Live audit query
- **WHEN** an audit-relevant event occurs in a running stack
- **THEN** a Loki query for its correlation ID (or event type) returns it within seconds, while the flow that caused it may still be in progress

### Requirement: Telemetry pipeline is smoke-tested
The smoke suite SHALL verify the pipeline end to end: a driven login flow yields a trace in Tempo, an audit-shaped log line is queryable in Loki, and Grafana serves the provisioned dashboard. Telemetry assertions MUST poll with a deadline (ingestion is asynchronous) rather than assert immediately.

#### Scenario: Pipeline smoke test
- **WHEN** the telemetry smoke tests run against a fresh stack
- **THEN** they find a login trace in Tempo, an expected log line in Loki, and the dashboard via Grafana's API, all within a bounded wait
