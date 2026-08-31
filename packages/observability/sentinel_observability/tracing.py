from __future__ import annotations

import logging
from typing import Any

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.propagate import extract, inject
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import SpanKind

from sentinel_observability.settings import get_observability_settings

logger = logging.getLogger(__name__)

_configured = False
_httpx_instrumented = False
_sqlalchemy_instrumented = False


def configure_tracing(service_name: str) -> None:
    global _configured
    if _configured:
        return

    settings = get_observability_settings()
    if not settings.otel_enabled or settings.otel_traces_exporter.lower() == "none":
        logger.info("OpenTelemetry tracing disabled for %s", service_name)
        _configured = True
        return

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(
        endpoint=settings.otel_exporter_otlp_endpoint,
        insecure=True,
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _configured = True
    logger.info(
        "OpenTelemetry tracing configured for %s -> %s",
        service_name,
        settings.otel_exporter_otlp_endpoint,
    )


def instrument_httpx() -> None:
    global _httpx_instrumented
    if _httpx_instrumented:
        return
    HTTPXClientInstrumentor().instrument()
    _httpx_instrumented = True


def instrument_sqlalchemy(engine: Any) -> None:
    global _sqlalchemy_instrumented
    if _sqlalchemy_instrumented:
        return
    SQLAlchemyInstrumentor().instrument(engine=engine)
    _sqlalchemy_instrumented = True


def get_tracer(name: str) -> trace.Tracer:
    return trace.get_tracer(name)


def inject_trace_context(carrier: dict[str, str]) -> None:
    inject(carrier)


def extract_trace_context(carrier: dict[str, str]) -> Any:
    return extract(carrier)


def start_consumer_span(
    tracer_name: str,
    span_name: str,
    carrier: dict[str, str] | None,
):
    tracer = get_tracer(tracer_name)
    context = extract_trace_context(carrier or {})
    return tracer.start_as_current_span(span_name, context=context, kind=SpanKind.CONSUMER)
