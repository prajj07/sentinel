from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


class FailureType(StrEnum):
    LATENCY = "latency"
    HTTP_500 = "http_500"
    SERVICE_UNAVAILABLE = "service_unavailable"


class ExperimentStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    STOPPED = "stopped"
    FAILED = "failed"


ALLOWED_SERVICES = frozenset({"gateway", "orders", "inventory", "payments"})


def new_experiment_id() -> str:
    return f"exp_{uuid4().hex[:8]}"


class InjectRequest(BaseModel):
    service: str
    type: FailureType
    duration_seconds: int = Field(ge=1, le=300)
    delay_ms: int | None = Field(default=None, ge=1, le=60_000)

    @field_validator("service")
    @classmethod
    def _known_service(cls, value: str) -> str:
        name = value.strip().lower()
        if name not in ALLOWED_SERVICES:
            raise ValueError(f"unsupported service '{value}'")
        return name

    @model_validator(mode="after")
    def _latency_needs_delay(self) -> InjectRequest:
        if self.type == FailureType.LATENCY and self.delay_ms is None:
            raise ValueError("delay_ms is required for latency experiments")
        return self


class ActiveRule(BaseModel):
    experiment_id: str
    service: str
    type: FailureType
    duration_seconds: int
    delay_ms: int | None = None
    started_at: datetime
    expires_at: datetime


class ExperimentRecord(BaseModel):
    id: str
    service: str
    type: FailureType
    duration_seconds: int
    delay_ms: int | None = None
    status: ExperimentStatus
    started_at: datetime
    ended_at: datetime | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    impact_summary: dict[str, Any] | None = None
    error: str | None = None


class ActivateRequest(BaseModel):
    experiment_id: str
    type: FailureType
    duration_seconds: int = Field(ge=1, le=300)
    delay_ms: int | None = Field(default=None, ge=1, le=60_000)


class InjectResponse(BaseModel):
    experiment_id: str
    service: str
    type: FailureType
    status: ExperimentStatus
    started_at: datetime
