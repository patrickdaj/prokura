"""Shared OpenTelemetry wiring for every Prokura Python service.

One module, imported by all services (it replaced six copied ``telemetry.py`` that
had drifted — a fix like the M9 metrics meter used to land in one and not the rest).

Design invariants (observability DoD):
- W3C ``traceparent`` is the cross-service join key. Trace↔log correlation uses the
  **native** OTel trace context — the ``trace_id``/``span_id`` the logging handler
  attaches to every audit record + a Grafana Tempo→Loki derived field — not a
  hand-copied correlation id. The domain ref (e.g. ``apr-…``) still rides as a span
  attribute so a flow is also findable by domain id.
- Traces are legible as a flow: the flow's root span carries ``prokura.flow`` (and
  ``user``/``agent``/``decision``); every deny/refusal flips the span red via
  :func:`record_decision` with ``deny=True``; domain decisions are span events.
- Fire-and-forget: batch/periodic exporters drop on failure and never block the
  request path; no service declares ``depends_on: lgtm`` and each stays healthy
  (and the smoke suite green) with the receiver stopped.
- Traces → Tempo, logs → Loki, metrics → Prometheus, all via OTLP gRPC to the
  otel-lgtm receiver.

Public API: :func:`setup`, :func:`tracer`, :func:`current_trace_id`,
:func:`stamp_flow`, :func:`record_decision`, :func:`record_stop_ms`.
"""

import logging
import os

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Link, SpanContext, Status, StatusCode, TraceFlags

_AUDIT_LOGGER = "prokura.audit"
_OTLP_ENDPOINT = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://lgtm:4317")

_service_name = "prokura"
_stop_ms_hist = None


def setup(app, service_name: str) -> logging.Logger:
    """Instrument a FastAPI app: traces → Tempo, logs → Loki, metrics → Prometheus.

    Returns the ``prokura.audit`` logger (also mirrored to stdout for ``docker logs``).
    Fire-and-forget throughout — every exporter drops on failure.
    """
    global _service_name, _stop_ms_hist
    _service_name = service_name
    resource = Resource.create({"service.name": service_name})

    # Traces -> Tempo. BatchSpanProcessor drops on export failure (fire-and-forget).
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=_OTLP_ENDPOINT, insecure=True))
    )
    trace.set_tracer_provider(tracer_provider)

    # Logs -> Loki. Same batch/drop semantics; attaches trace context automatically,
    # which is the native trace_id the Grafana derived field joins on.
    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(
        BatchLogRecordProcessor(OTLPLogExporter(endpoint=_OTLP_ENDPOINT, insecure=True))
    )
    otel_handler = LoggingHandler(level=logging.INFO, logger_provider=logger_provider)

    audit_logger = logging.getLogger(_AUDIT_LOGGER)
    audit_logger.setLevel(logging.INFO)
    audit_logger.addHandler(otel_handler)
    audit_logger.addHandler(logging.StreamHandler())  # also to stdout for docker logs
    audit_logger.propagate = False

    # Metrics -> Prometheus (via the LGTM OTLP receiver). Fire-and-forget: the periodic
    # reader drops on export failure. M9 records the revocation time-to-stop here so the
    # operator dashboard can graph "how fast to stop" (only the broker records to it).
    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[PeriodicExportingMetricReader(
            OTLPMetricExporter(endpoint=_OTLP_ENDPOINT, insecure=True),
            export_interval_millis=10_000)],
    )
    metrics.set_meter_provider(meter_provider)
    _stop_ms_hist = meter_provider.get_meter(f"prokura.{service_name}").create_histogram(
        "prokura.revocation.stop_ms", unit="ms",
        description="Time from revoke to the agent losing the ability to be issued or "
                    "re-acquire authority (the kill switch's measured time-to-stop).")

    FastAPIInstrumentor.instrument_app(app)
    HTTPXClientInstrumentor().instrument()
    return audit_logger


def tracer():
    """The service's tracer (named ``prokura.<service>`` from the last :func:`setup`)."""
    return trace.get_tracer(f"prokura.{_service_name}")


def current_trace_id() -> str:
    """The active span's trace id in hex (032x) — the native cross-service join key,
    also emitted on every audit log record by the OTel logging handler."""
    span = trace.get_current_span()
    ctx = span.get_span_context()
    if ctx and ctx.trace_id:
        return format(ctx.trace_id, "032x")
    return ""


def current_span_id() -> str:
    """The active span's span id in hex (016x) — persist it (with the trace id) to
    later :func:`link_to` an async leg that can't inherit trace context."""
    span = trace.get_current_span()
    ctx = span.get_span_context()
    if ctx and ctx.span_id:
        return format(ctx.span_id, "016x")
    return ""


def link_to(trace_id_hex: str, span_id_hex: str):
    """Build an OTel **Link** to a span identified by persisted hex ids.

    Used to join ceremony legs that cross a transport which can't forward
    traceparent (e.g. Keycloak's CIBA callback, a FastAPI background task): the
    originating span's ``{trace_id, span_id}`` are stored on the row, and every
    later leg is created ``links=[link_to(...)]`` so the whole flow is navigable
    from the origin trace. Returns ``None`` if either id is missing.
    """
    if not trace_id_hex or not span_id_hex:
        return None
    try:
        ctx = SpanContext(
            trace_id=int(trace_id_hex, 16),
            span_id=int(span_id_hex, 16),
            is_remote=True,
            trace_flags=TraceFlags(TraceFlags.SAMPLED),
        )
    except (ValueError, TypeError):
        return None
    return Link(ctx)


def stamp_flow(flow: str, *, span=None, user: str = None, agent: str = None, **attrs) -> None:
    """Tag a flow's **root span** so ``{ prokura.flow = "X" }`` in Tempo lands on one
    clean end-to-end trace. Health-check / noise traces never call this, so they carry
    no flow tag and stay out of the results. ``span`` defaults to the active span.
    """
    if span is None:
        span = trace.get_current_span()
    span.set_attribute("prokura.flow", flow)
    if user is not None:
        span.set_attribute("prokura.user", user)
    if agent is not None:
        span.set_attribute("prokura.agent", agent)
    for k, v in attrs.items():
        if v is not None:
            span.set_attribute(f"prokura.{k}", v)


# Substrings that mark a decision code as a denial/failure (→ red span). Matches
# denied_*, *_refused, *_failed, error, *_mismatch, expired, ceremony_error, the
# human "denied" verdict, etc. Success/neutral codes (issued, approved, consumed,
# revoked, linked, retrieved, …) contain none of these.
_DENY_MARKERS = ("denied", "refused", "failed", "error", "mismatch", "expired")


def is_denial(code: str) -> bool:
    """True if a decision code denotes a refusal/failure (so the span goes red)."""
    return any(marker in code for marker in _DENY_MARKERS)


def record_decision(code: str, *, span=None, deny: bool = False, **attrs) -> None:
    """Record a domain decision as a span **event** so the trace narrates itself.

    ``issued`` / ``approved`` / ``consumed`` / ``revoked`` / ``linked`` land as events;
    every deny/refusal (wrong audience, no grant, ``not_consented``, revoked, expired,
    …) with ``deny=True`` additionally flips the span **red** (``Status(ERROR, code)``)
    with a machine-readable reason, so the failure is visible in the waterfall.

    ``span`` defaults to the active span; on a non-recording span (e.g. outside a
    request) the calls are harmless no-ops.
    """
    if span is None:
        span = trace.get_current_span()
    event_attrs = {"prokura.decision": code}
    for k, v in attrs.items():
        if v is not None:
            event_attrs[k if k.startswith("prokura.") else f"prokura.{k}"] = v
    span.set_attribute("prokura.decision", code)
    if deny:
        span.set_status(Status(StatusCode.ERROR, code))
        span.add_event("denied", event_attrs)
    else:
        span.add_event(code, event_attrs)


def record_stop_ms(ms: int, *, agent: str) -> None:
    """M9: record the revocation time-to-stop so the dashboard can surface it."""
    if _stop_ms_hist is not None:
        _stop_ms_hist.record(ms, {"agent": agent})
