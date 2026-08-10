# observability — delta (refactor-observability-and-packaging)

## ADDED Requirements

### Requirement: Traces are legible and flow-scoped
Every flow's **root span** SHALL carry a `prokura.flow` attribute (a stable flow identifier
such as A/B/C/D or a surface name) plus the acting `prokura.user` and `prokura.agent`, so a
single trace for one logical action is discoverable by flow in the trace backend. Every
deny/refusal path SHALL set the span status to error with a machine-readable reason, and the
domain decisions (issuance, approval, consumption, revocation, linking, denials) SHALL be
recorded as **span events** with their attributes, so the trace narrates the action without a
separate log lookup. Async ceremony legs that cannot share trace context across a transport
(e.g. the CIBA register → delegate → decide → complete sequence, and background tasks) SHALL
be joined with span **links** to the originating span, so the whole flow is navigable as one
story.

#### Scenario: Find one flow end-to-end by its tag
- **WHEN** a user searches the trace backend for a given `prokura.flow`
- **THEN** a single end-to-end trace for that flow is returned, and health-check / noise
  traces (which carry no flow tag) are excluded

#### Scenario: A denied step is visibly red
- **WHEN** a flow is refused at some step (e.g. wrong audience, missing consent, revoked)
- **THEN** the corresponding span has error status with the reason, and a `denied` span event
  carries the machine-readable code — the failure is visible in the waterfall, not green

#### Scenario: The trace narrates the decision
- **WHEN** a traced flow makes a domain decision (issued / approved / consumed / revoked)
- **THEN** that decision is present as a span event on the trace, so the story is readable in
  the trace alone

#### Scenario: The ceremony is navigable as one flow
- **WHEN** an approval ceremony spans the register request, Keycloak's callback, the decision,
  and the background completion
- **THEN** the later legs link back to the originating span, so the ceremony is reachable as
  one navigable flow despite crossing transports

## MODIFIED Requirements

### Requirement: End-to-end trace propagation with correlation IDs
Every cross-service flow SHALL propagate W3C Trace Context (`traceparent`) across all
participating services, so a single trace links Keycloak, OpenFGA, OpenBao, broker, and
approval activity for one logical action. Trace↔log correlation SHALL use the **native OTel
trace context** — the `trace_id`/`span_id` attached to every audit log record by the logging
handler, joined in the trace backend by a Tempo→Loki derived field — rather than a
hand-copied correlation identifier. Domain correlation identifiers (the human-approval
reference ID) SHALL still ride as span attributes so a flow is also findable by domain ID.
All Prokura-built services MUST be OTel-instrumented from their first commit (definition of
done), via the shared telemetry module.

#### Scenario: One flow, one trace
- **WHEN** an agent completes a flow that touches more than one service (e.g., token exchange
  followed by a broker call)
- **THEN** a single trace exists containing spans from each participating service, joined by
  the propagated trace context

#### Scenario: Trace joins its logs natively
- **WHEN** a span in a traced flow is selected in the trace backend
- **THEN** its correlated audit log lines are reachable by the native trace id (Tempo→Loki
  derived field), without a hand-maintained correlation-id copy

#### Scenario: Domain IDs joined to the trace
- **WHEN** an approval reference ID is created inside a traced flow
- **THEN** the trace's spans carry that identifier as an attribute, and searching the trace
  backend by it finds the trace

### Requirement: Bundled receiver with provisioned dashboard
The compose stack SHALL include a single dev-mode LGTM receiver (Grafana + Tempo + Loki +
Prometheus) with datasources pre-provisioned (including a Tempo→Loki derived field on the
trace id) and a "delegation chain" dashboard bundled from the repo — no manual Grafana setup.
Grafana (its Explore views + the provisioned dashboard) is the **primary human-facing
observability surface**; there is no separate bespoke console. The provisioned dashboard MUST
actually render (verified visually, not only via the dashboards API). The stack MUST remain
functional if the receiver is down (telemetry is fire-and-forget; no service depends on it).

#### Scenario: Zero-setup observability
- **WHEN** the stack comes up from a clean clone and a user opens Grafana
- **THEN** the delegation-chain dashboard exists and renders against pre-provisioned
  datasources, and the trace→logs derived field works, without any manual configuration

#### Scenario: Telemetry outage is non-fatal
- **WHEN** the receiver container is stopped
- **THEN** logins, FGA checks, and Bao operations continue to succeed

### Requirement: Trace-to-logs correlation jump
A user SHALL be able to move from a selected trace or span to its **correlated audit log
lines** in one step, using Grafana's Tempo→Loki derived field on the native trace id (the
same trace context propagated across services). This closes the loop from "what happened"
(the trace) to "the audit record of it" (the logs). Log lines MUST NOT expose secrets or
request parameters beyond what the audit events already contain.

#### Scenario: Jump from a span to its audit logs
- **WHEN** a user selects a span in a traced flow in Grafana
- **THEN** the Loki audit lines for that trace id are reachable via the derived-field jump, so
  the trace and its audit record are visible together

#### Scenario: Absent correlation is handled gracefully
- **WHEN** a selected span has no correlated audit lines
- **THEN** the jump yields an empty result state rather than an unfiltered log dump

## REMOVED Requirements

### Requirement: Bespoke console is the headline view
**Reason**: The bespoke console (`services/console`, :8095) reimplemented the trace waterfall,
service filtering, and trace→logs jump that Grafana + Tempo + Loki already provide natively
and better — it was duplicate, drift-prone maintenance surface (its own docstring called it
"the headline demo view; Grafana stays for power-user drill-down"). Removed in favour of
Grafana as the single observability surface.
**Migration**: Use Grafana **Explore → Tempo** for the flow waterfall (searchable by
`prokura.flow`), the provisioned **delegation-chain dashboard** for the overview, and the
**Tempo→Loki derived field** for the trace→logs jump. The curated demo narrative lives in the
walkthroughs with real Grafana/Tempo/Loki screenshots. All `:8095` references are removed.
