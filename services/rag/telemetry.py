"""OpenTelemetry wiring for the RAG retriever — the born-instrumented pattern
every Prokura Python service has copied since the token broker (M2).

Design invariants (observability DoD):
- W3C ``traceparent`` is the join key across services; the domain correlation id
  rides as span attribute ``prokura.correlation_id`` AND as a field on every
  structured ``rag_audit`` log line, so the flow ``mcp -> rag -> openfga`` is
  joinable in Tempo and watchable in Loki.
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
    return trace.get_tracer("prokura.rag")


def current_traceparent() -> str:
    """The active span's trace id in hex — used as the correlation id so mcp, rag,
    and OpenFGA share one join key across the retrieval flow."""
    span = trace.get_current_span()
    ctx = span.get_span_context()
    if ctx and ctx.trace_id:
        return format(ctx.trace_id, "032x")
    return ""
