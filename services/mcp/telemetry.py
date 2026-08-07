"""OpenTelemetry wiring for the MCP server — copies the token-broker/approval
pattern (M2/M3) so the M4 flow joins the same trace + Loki audit.

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

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import (
    OTLPLogExporter,
)
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

import config

_AUDIT_LOGGER = "prokura.audit"


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

    FastAPIInstrumentor.instrument_app(app)
    HTTPXClientInstrumentor().instrument()
    return audit_logger


def tracer():
    return trace.get_tracer("prokura.mcp")


def current_traceparent() -> str:
    """The active span's trace id in hex — the correlation id, so the MCP tool
    call, the broker/tools-api hops, and the approval events share one join key."""
    span = trace.get_current_span()
    ctx = span.get_span_context()
    if ctx and ctx.trace_id:
        return format(ctx.trace_id, "032x")
    return ""
