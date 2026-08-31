from __future__ import annotations

import logging

from fastapi import FastAPI

from sentinel_chaos.middleware import build_chaos_middleware
from sentinel_chaos.metrics import CHAOS_ACTIVE_EXPERIMENTS
from sentinel_chaos.routes import router
from sentinel_chaos.settings import get_chaos_settings

logger = logging.getLogger(__name__)

_configured: set[str] = set()


def configure_chaos(app: FastAPI, *, service_name: str) -> None:
    """Install inbound chaos middleware and internal control routes.

    Register before ``configure_observability`` so Prometheus HTTP duration
    includes injected latency.
    """
    if service_name in _configured:
        return

    settings = get_chaos_settings()
    app.state.chaos_service_name = service_name
    CHAOS_ACTIVE_EXPERIMENTS.labels(service_name).set(0)
    app.include_router(router)
    app.middleware("http")(build_chaos_middleware(service_name))
    _configured.add(service_name)
    logger.info(
        "Chaos configured for service=%s enabled=%s",
        service_name,
        settings.chaos_enabled,
    )
