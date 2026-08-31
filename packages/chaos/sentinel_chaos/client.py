from __future__ import annotations

from typing import Any

import httpx

from sentinel_chaos.models import ActivateRequest, FailureType

TARGET_URLS = {
    "gateway": "http://gateway:8000",
    "orders": "http://orders:8001",
    "inventory": "http://inventory:8002",
    "payments": "http://payments:8003",
}


class ChaosTargetClient:
    def __init__(self, base_urls: dict[str, str] | None = None, timeout: float = 5.0) -> None:
        self._urls = base_urls or TARGET_URLS
        self._timeout = timeout

    def _url(self, service: str, path: str) -> str:
        base = self._urls[service].rstrip("/")
        return f"{base}{path}"

    def activate(
        self,
        service: str,
        *,
        experiment_id: str,
        failure_type: FailureType,
        duration_seconds: int,
        delay_ms: int | None,
    ) -> dict[str, Any]:
        payload = ActivateRequest(
            experiment_id=experiment_id,
            type=failure_type,
            duration_seconds=duration_seconds,
            delay_ms=delay_ms,
        )
        with httpx.Client(timeout=self._timeout) as client:
            response = client.post(
                self._url(service, "/internal/chaos/activate"),
                json=payload.model_dump(mode="json"),
            )
        response.raise_for_status()
        return response.json()

    def deactivate(self, service: str, experiment_id: str, *, force: bool = False) -> dict[str, Any]:
        with httpx.Client(timeout=self._timeout) as client:
            response = client.post(
                self._url(service, "/internal/chaos/deactivate"),
                params={"experiment_id": experiment_id, "force": str(force).lower()},
            )
        response.raise_for_status()
        return response.json()

    def deactivate_any(self, service: str) -> dict[str, Any]:
        with httpx.Client(timeout=self._timeout) as client:
            response = client.post(
                self._url(service, "/internal/chaos/deactivate"),
                params={"force": "true"},
            )
        response.raise_for_status()
        return response.json()
