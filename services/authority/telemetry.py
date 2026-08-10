"""OpenTelemetry wiring for the authority console — the shared per-service
pattern (broker M2 / approval M3 / MCP M4). Fire-and-forget: batch exporters
drop on failure and never block the request path, so there is no
``depends_on: lgtm`` and the service stays healthy with lgtm stopped.

Traces -> Tempo, logs -> Loki, both OTLP gRPC to the otel-lgtm receiver; the
W3C ``traceparent`` is the cross-service join key and ``prokura.correlation_id``
rides on every audit line."""

import logging

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
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

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=config.OTLP_ENDPOINT, insecure=True))
    )
    trace.set_tracer_provider(tracer_provider)

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
    return trace.get_tracer("prokura.authority")


def current_traceparent() -> str:
    span = trace.get_current_span()
    ctx = span.get_span_context()
    if ctx and ctx.trace_id:
        return format(ctx.trace_id, "032x")
    return ""
