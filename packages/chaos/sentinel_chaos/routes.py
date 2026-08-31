from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request

from sentinel_chaos.metrics import CHAOS_ACTIVE_EXPERIMENTS, CHAOS_INJECTIONS
from sentinel_chaos.models import ActivateRequest, ActiveRule
from sentinel_chaos.settings import get_chaos_settings
from sentinel_chaos.store import store

router = APIRouter(prefix="/internal/chaos", tags=["chaos-internal"])


def _enabled() -> None:
    if not get_chaos_settings().chaos_enabled:
        raise HTTPException(status_code=404, detail="Chaos is disabled")


def _service_name(request: Request) -> str:
    return getattr(request.app.state, "chaos_service_name", "unknown")


@router.post("/activate")
def activate(payload: ActivateRequest, request: Request) -> dict:
    _enabled()
    service_name = _service_name(request)
    current = store.get_active()
    if current is not None:
        raise HTTPException(
            status_code=409,
            detail=f"experiment {current.experiment_id} already running",
        )
    now = datetime.now(timezone.utc)
    rule = ActiveRule(
        experiment_id=payload.experiment_id,
        service=service_name,
        type=payload.type,
        duration_seconds=payload.duration_seconds,
        delay_ms=payload.delay_ms,
        started_at=now,
        expires_at=now + timedelta(seconds=payload.duration_seconds),
    )
    store.activate(rule)
    CHAOS_INJECTIONS.labels(service_name, payload.type.value).inc()
    CHAOS_ACTIVE_EXPERIMENTS.labels(service_name).set(1)
    return rule.model_dump(mode="json")


@router.post("/deactivate")
def deactivate(request: Request, experiment_id: str | None = None, force: bool = False) -> dict:
    _enabled()
    service_name = _service_name(request)
    if force:
        cleared = store.deactivate_any()
    else:
        cleared = store.deactivate(experiment_id)
    CHAOS_ACTIVE_EXPERIMENTS.labels(service_name).set(0 if store.get_active() is None else 1)
    if cleared is None:
        return {"deactivated": False}
    return {"deactivated": True, "experiment_id": cleared.experiment_id}


@router.get("/active")
def active() -> dict:
    _enabled()
    rule = store.get_active()
    if rule is None:
        return {"active": False}
    return {"active": True, "rule": rule.model_dump(mode="json")}
