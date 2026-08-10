"""OpenTelemetry wiring for the token broker — the first instrumented Python
service in Prokura, and the pattern the approval (M3) and MCP (M4) services copy.

Design invariants (observability DoD):
- W3C ``traceparent`` is the join key across services; the domain correlation id
  rides as span attribute ``prokura.correlation_id`` AND as a field on every
  structured audit log line, so a flow is joinable in Tempo and watchable in Loki.
- Fire-and-forget: exporters use batch processors that drop on failure and never
  block the request path; the service has NO ``depends_on: lgtm`` and stays
  healthy (and the smoke suite green) with lgtm stopped.
- Traces -> Tempo, logs -> Loki, both via OTLP gRPC to the otel-lgtm receiver.
"""

import logging

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import (
    OTLPLogExporter,
)
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
    OTLPMetricExporter,
)
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

import config

_AUDIT_LOGGER = "prokura.audit"
_stop_ms_hist = None


def setup_telemetry(app) -> logging.Logger:
    resource = Resource.create({"service.name": config.SERVICE_NAME})

    # Traces -> Tempo. BatchSpanProcessor drops on export failure (fire-and-forget).
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=config.OTLP_ENDPOINT, insecure=True))
    )
    trace.set_tracer_provider(tracer_provider)

    # Logs -> Loki. Same batch/drop semantics; attaches trace context automatically.
    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(
        BatchLogRecordProcessor(OTLPLogExporter(endpoint=config.OTLP_ENDPOINT, insecure=True))
    )
    otel_handler = LoggingHandler(level=logging.INFO, logger_provider=logger_provider)

    audit_logger = logging.getLogger(_AUDIT_LOGGER)
    audit_logger.setLevel(logging.INFO)
    audit_logger.addHandler(otel_handler)
    audit_logger.addHandler(logging.StreamHandler())  # also to stdout for docker logs
    audit_logger.propagate = False

    # Metrics -> Prometheus (via the LGTM OTLP receiver). Fire-and-forget: the
    # periodic reader drops on export failure. M9 records the revocation
    # time-to-stop here so the operator dashboard can graph "how fast to stop".
    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[PeriodicExportingMetricReader(
            OTLPMetricExporter(endpoint=config.OTLP_ENDPOINT, insecure=True),
            export_interval_millis=10_000)],
    )
    metrics.set_meter_provider(meter_provider)
    global _stop_ms_hist
    _stop_ms_hist = meter_provider.get_meter("prokura.token-broker").create_histogram(
        "prokura.revocation.stop_ms", unit="ms",
        description="Time from revoke to the agent losing the ability to be issued or "
                    "re-acquire authority (the kill switch's measured time-to-stop).")

    FastAPIInstrumentor.instrument_app(app)
    HTTPXClientInstrumentor().instrument()
    return audit_logger


def record_stop_ms(ms: int, *, agent: str) -> None:
    """M9: record the revocation time-to-stop so the dashboard can surface it."""
    if _stop_ms_hist is not None:
        _stop_ms_hist.record(ms, {"agent": agent})


def tracer():
    return trace.get_tracer("prokura.token-broker")


def current_traceparent() -> str:
    """The active span's trace id in hex — used as the correlation id so broker,
    Keycloak, and (later) approval events share one join key."""
    span = trace.get_current_span()
    ctx = span.get_span_context()
    if ctx and ctx.trace_id:
        return format(ctx.trace_id, "032x")
    return ""
