from __future__ import annotations

import json
from typing import Any

import httpx

from sentinel_common.settings import get_http_settings


class DownstreamError(Exception):
    def __init__(self, message: str, status_code: int = 502, body: Any | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class DownstreamTimeoutError(DownstreamError):
    def __init__(self, message: str = "Downstream request timed out") -> None:
        super().__init__(message, status_code=504)


async def request_json(
    method: str,
    url: str,
    *,
    json_body: dict[str, Any] | None = None,
    timeout_seconds: float | None = None,
) -> tuple[int, Any]:
    settings = get_http_settings()
    timeout = timeout_seconds if timeout_seconds is not None else settings.http_timeout_seconds

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(method, url, json=json_body)
    except httpx.TimeoutException as exc:
        raise DownstreamTimeoutError() from exc
    except httpx.HTTPError as exc:
        raise DownstreamError(f"Downstream request failed: {exc}") from exc

    try:
        payload = response.json()
    except json.JSONDecodeError:
        payload = response.text

    return response.status_code, payload
