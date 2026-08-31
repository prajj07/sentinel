from __future__ import annotations

import logging

from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from sentinel_observability.metrics import mount_metrics
from sentinel_observability.tracing import configure_tracing, instrument_httpx

logger = logging.getLogger(__name__)

_observability_configured: set[str] = set()


def configure_observability(app: FastAPI, *, service_name: str) -> None:
    """Configure OTel traces, HTTP metrics, and /metrics for a Sentinel service."""
    if service_name in _observability_configured:
        return

    configure_tracing(service_name)
    instrument_httpx()
    mount_metrics(app)
    FastAPIInstrumentor.instrument_app(app)

    _observability_configured.add(service_name)
    logger.info("Observability configured for service=%s", service_name)
