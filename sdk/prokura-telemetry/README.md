# prokura-telemetry

Shared OpenTelemetry wiring for every Prokura Python service — one installable module
that replaced six copied `telemetry.py` (which had drifted, so a fix landed in one and
not the rest).

Each service installs it (`pip install ./sdk/prokura-telemetry`, from a repo-root Docker
build context) and imports:

```python
from prokura_telemetry import setup, tracer, current_trace_id, record_decision

audit = setup(app, "token-broker")          # traces→Tempo, logs→Loki, metrics→Prometheus
with tracer().start_as_current_span("..."):
    ...
```

## API

- `setup(app, service_name) -> logging.Logger` — instrument a FastAPI app; returns the
  `prokura.audit` logger (also mirrored to stdout). Fire-and-forget: every exporter drops
  on failure and never blocks the request path.
- `tracer()` — the service's tracer (`prokura.<service>`).
- `current_trace_id()` — the active trace id in hex; the native cross-service join key,
  also stamped on every audit log record by the OTel logging handler (this is what the
  Grafana Tempo→Loki derived field joins on).
- `stamp_flow(flow, *, span=None, user=None, agent=None, **attrs)` — tag a flow's **root
  span** (the active span by default) so `{ prokura.flow = "X" }` in Tempo returns exactly
  that end-to-end trace.
- `record_decision(code, *, span=None, deny=False, **attrs)` — record a domain decision
  as a span **event** (on the active span by default); with `deny=True` also sets the span
  status to error (red in the waterfall) with a machine-readable reason.
- `is_denial(code)` — True if a decision code denotes a refusal/failure; services pass its
  result as `deny=` so every deny path goes red without threading a flag through call sites.
- `record_stop_ms(ms, *, agent)` — M9 revocation time-to-stop histogram (broker only).

## Invariants

- **Native correlation.** Trace↔log join is the OTel `trace_id`, not a hand-copied id.
  The domain ref still rides as a span attribute for domain search.
- **Fire-and-forget.** No service declares `depends_on: lgtm`; the stack stays healthy
  and the smoke suite green with the receiver stopped.
- **Born instrumented.** All Prokura-built services call `setup()` from their first commit.
