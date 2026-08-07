# ADR-0017: Every service is born instrumented; telemetry is fire-and-forget

- **Status:** accepted
- **Source of truth:** `openspec/specs/observability/spec.md`; `services/*/telemetry.py`

## Context

Observability could have been a late add-on. The demo's credibility depends on showing the flow as one joinable trace with live audit.

## Decision

**Every new service is born instrumented** (M2 onward): OTel traces→Tempo, logs→Loki over OTLP; the W3C `traceparent` is the cross-service join key and the domain correlation id rides as a span attribute AND on every audit line. Exporters are **fire-and-forget** (batch/drop, no `depends_on: lgtm`) so the stack stays healthy with the telemetry receiver stopped.

## Alternatives considered

- Bolt on observability at the end: misses the per-service instrumentation and the born-instrumented discipline.

## Consequences

Any flow is joinable in Tempo and watchable in Loki; the smoke suite stays green with lgtm stopped (verified per milestone). Observability is a definition-of-done, not a milestone.

