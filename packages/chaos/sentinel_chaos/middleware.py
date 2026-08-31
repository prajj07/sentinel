from __future__ import annotations

import asyncio
import logging

from starlette.requests import Request
from starlette.responses import JSONResponse

from sentinel_chaos.metrics import CHAOS_REQUESTS_AFFECTED
from sentinel_chaos.models import FailureType
from sentinel_chaos.settings import get_chaos_settings
from sentinel_chaos.store import store

logger = logging.getLogger(__name__)

EXEMPT_PATHS = frozenset({"/health", "/metrics"})
EXEMPT_PREFIXES = ("/internal/chaos",)


def _is_exempt(path: str) -> bool:
    if path in EXEMPT_PATHS:
        return True
    return any(path.startswith(prefix) for prefix in EXEMPT_PREFIXES)


def _chaos_span(experiment_id: str, failure_type: str):
    try:
        from opentelemetry import trace

        tracer = trace.get_tracer("sentinel.chaos")
        return tracer.start_as_current_span(
            "chaos.inject",
            attributes={
                "chaos.experiment_id": experiment_id,
                "chaos.failure_type": failure_type,
            },
        )
    except Exception:
        from contextlib import nullcontext

        return nullcontext()


def build_chaos_middleware(service_name: str):
    async def chaos_middleware(request: Request, call_next):
        if not get_chaos_settings().chaos_enabled or _is_exempt(request.url.path):
            return await call_next(request)

        rule = store.get_active()
        if rule is None:
            return await call_next(request)

        CHAOS_REQUESTS_AFFECTED.labels(service_name, rule.type.value).inc()
        logger.info(
            "chaos_applied service=%s experiment_id=%s type=%s path=%s",
            service_name,
            rule.experiment_id,
            rule.type.value,
            request.url.path,
        )

        with _chaos_span(rule.experiment_id, rule.type.value):
            if rule.type == FailureType.LATENCY:
                delay_s = (rule.delay_ms or 0) / 1000.0
                await asyncio.sleep(delay_s)
                return await call_next(request)

            if rule.type == FailureType.HTTP_500:
                return JSONResponse(
                    status_code=500,
                    content={
                        "detail": "chaos injected HTTP 500",
                        "experiment_id": rule.experiment_id,
                    },
                )

            if rule.type == FailureType.SERVICE_UNAVAILABLE:
                return JSONResponse(
                    status_code=503,
                    content={
                        "detail": "chaos injected service unavailable",
                        "experiment_id": rule.experiment_id,
                    },
                )

            return await call_next(request)

    return chaos_middleware
