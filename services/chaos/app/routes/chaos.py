from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.registry import registry
from app.scenarios.payment_degradation import run_payment_degradation
from sentinel_chaos.client import ChaosTargetClient
from sentinel_chaos.models import (
    ExperimentRecord,
    ExperimentStatus,
    InjectRequest,
    InjectResponse,
    new_experiment_id,
)


class ScenarioRequest(BaseModel):
    delay_ms: int = Field(default=3000, ge=100, le=10_000)
    duration_seconds: int = Field(default=30, ge=5, le=120)
    baseline_orders: int = Field(default=6, ge=1, le=50)
    traffic_orders: int = Field(default=8, ge=1, le=50)
    recovery_orders: int = Field(default=4, ge=1, le=50)

router = APIRouter()
_client = ChaosTargetClient()
_auto_stop_tasks: dict[str, asyncio.Task] = {}


def _client_for_request() -> ChaosTargetClient:
    from app.config import get_settings

    settings = get_settings()
    return ChaosTargetClient(
        {
            "gateway": settings.gateway_url,
            "orders": settings.orders_url,
            "inventory": settings.inventory_url,
            "payments": settings.payments_url,
        }
    )


async def _auto_complete(experiment_id: str, service: str, delay: int) -> None:
    await asyncio.sleep(delay)
    record = registry.get(experiment_id)
    if record is None or record.status != ExperimentStatus.RUNNING:
        return
    try:
        _client_for_request().deactivate(service, experiment_id)
    except Exception:
        pass
    registry.update_status(experiment_id, ExperimentStatus.COMPLETED)


@router.post("/chaos/inject", response_model=InjectResponse)
async def inject_failure(payload: InjectRequest) -> InjectResponse:
    experiment_id = new_experiment_id()
    now = datetime.now(timezone.utc)
    record = ExperimentRecord(
        id=experiment_id,
        service=payload.service,
        type=payload.type,
        duration_seconds=payload.duration_seconds,
        delay_ms=payload.delay_ms,
        status=ExperimentStatus.RUNNING,
        started_at=now,
        parameters={
            "duration_seconds": payload.duration_seconds,
            "delay_ms": payload.delay_ms,
        },
    )
    registry.add(record)
    client = _client_for_request()
    try:
        client.deactivate_any(payload.service)
        client.activate(
            payload.service,
            experiment_id=experiment_id,
            failure_type=payload.type,
            duration_seconds=payload.duration_seconds,
            delay_ms=payload.delay_ms,
        )
    except Exception as exc:
        registry.update_status(experiment_id, ExperimentStatus.FAILED, error=str(exc))
        raise HTTPException(status_code=502, detail=f"failed to activate chaos: {exc}") from exc

    task = asyncio.create_task(_auto_complete(experiment_id, payload.service, payload.duration_seconds))
    _auto_stop_tasks[experiment_id] = task
    return InjectResponse(
        experiment_id=experiment_id,
        service=payload.service,
        type=payload.type,
        status=ExperimentStatus.RUNNING,
        started_at=now,
    )


@router.post("/chaos/stop/{experiment_id}")
async def stop_experiment(experiment_id: str) -> ExperimentRecord:
    record = registry.get(experiment_id)
    if record is None:
        raise HTTPException(status_code=404, detail="experiment not found")
    task = _auto_stop_tasks.pop(experiment_id, None)
    if task is not None:
        task.cancel()
    try:
        _client_for_request().deactivate(record.service, experiment_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"failed to deactivate chaos: {exc}") from exc
    if record.status == ExperimentStatus.RUNNING:
        updated = registry.update_status(experiment_id, ExperimentStatus.STOPPED)
        return updated or record
    return record


@router.get("/chaos/experiments")
def list_experiments() -> list[ExperimentRecord]:
    return registry.list()


@router.get("/chaos/experiments/{experiment_id}")
def get_experiment(experiment_id: str) -> ExperimentRecord:
    record = registry.get(experiment_id)
    if record is None:
        raise HTTPException(status_code=404, detail="experiment not found")
    return record


@router.post("/chaos/scenarios/payment-degradation")
async def payment_degradation_scenario(payload: ScenarioRequest | None = None) -> dict:
    params = payload or ScenarioRequest()

    async def inject(body: dict) -> dict:
        response = await inject_failure(InjectRequest.model_validate(body))
        return response.model_dump(mode="json")

    async def stop(experiment_id: str) -> ExperimentRecord:
        return await stop_experiment(experiment_id)

    result = await run_payment_degradation(
        inject=inject,
        stop=stop,
        delay_ms=params.delay_ms,
        duration_seconds=params.duration_seconds,
        baseline_orders=params.baseline_orders,
        traffic_orders=params.traffic_orders,
        recovery_orders=params.recovery_orders,
    )
    registry.update_status(
        result["experiment_id"],
        ExperimentStatus.COMPLETED,
        impact_summary=result.get("impact_summary"),
    )
    return result
