"""Sprint 2 observability integration tests (stack + Tempo must be running)."""

from __future__ import annotations

import os
import time

import httpx
import pytest

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8000")
ORDERS_URL = os.getenv("ORDERS_URL", "http://localhost:8001")
INVENTORY_URL = os.getenv("INVENTORY_URL", "http://localhost:8002")
PAYMENTS_URL = os.getenv("PAYMENTS_URL", "http://localhost:8003")
NOTIFICATIONS_URL = os.getenv("NOTIFICATIONS_URL", "http://localhost:8004")
PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090")
TEMPO_URL = os.getenv("TEMPO_URL", "http://localhost:3200")

TIMEOUT = httpx.Timeout(15.0)

SERVICE_BASES = (
    (GATEWAY_URL, "gateway"),
    (ORDERS_URL, "orders"),
    (INVENTORY_URL, "inventory"),
    (PAYMENTS_URL, "payments"),
    (NOTIFICATIONS_URL, "notifications"),
)


@pytest.fixture(scope="session")
def http() -> httpx.Client:
    with httpx.Client(timeout=TIMEOUT) as client:
        yield client


def _metrics_text(http: httpx.Client, base: str) -> str:
    response = http.get(f"{base}/metrics")
    assert response.status_code == 200, response.text
    return response.text


def test_metrics_endpoint_all_services(http: httpx.Client) -> None:
    for base, _ in SERVICE_BASES:
        body = _metrics_text(http, base)
        assert "http_requests_total" in body


def test_business_metrics_present(http: httpx.Client) -> None:
    orders_metrics = _metrics_text(http, ORDERS_URL)
    assert "orders_created_total" in orders_metrics
    assert "orders_failed_total" in orders_metrics
    assert "order_duration_seconds" in orders_metrics

    payments_metrics = _metrics_text(http, PAYMENTS_URL)
    assert "payments_total" in payments_metrics
    assert "payment_duration_seconds" in payments_metrics

    inventory_metrics = _metrics_text(http, INVENTORY_URL)
    assert "inventory_reservations_total" in inventory_metrics
    assert "inventory_releases_total" in inventory_metrics


def test_prometheus_targets_up(http: httpx.Client) -> None:
    response = http.get(f"{PROMETHEUS_URL}/api/v1/targets")
    assert response.status_code == 200
    targets = response.json()["data"]["activeTargets"]
    jobs = {t["labels"].get("job") for t in targets}
    for job in (
        "sentinel-gateway",
        "sentinel-orders",
        "sentinel-inventory",
        "sentinel-payments",
        "sentinel-notifications",
    ):
        assert job in jobs


def _wait_for_order_trace(http: httpx.Client, timeout: float = 45.0) -> str:
    """Return a trace ID for a distributed POST /orders request."""
    required = ("gateway", "orders", "inventory", "payments", "notifications")
    deadline = time.time() + timeout
    while time.time() < deadline:
        for service in ("gateway", "orders"):
            response = http.get(
                f"{TEMPO_URL}/api/search",
                params={"tags": f"service.name={service}", "limit": 20},
            )
            if response.status_code != 200:
                continue
            for trace in response.json().get("traces", []):
                if trace.get("rootTraceName") != "POST /orders":
                    continue
                trace_id = trace["traceID"]
                detail = http.get(f"{TEMPO_URL}/api/traces/{trace_id}")
                if detail.status_code != 200:
                    continue
                blob = detail.text.lower()
                if all(name in blob for name in required):
                    return trace_id
        time.sleep(2)
    raise AssertionError("No distributed POST /orders trace found in Tempo")


def test_trace_propagation(http: httpx.Client) -> None:
    response = http.post(
        f"{GATEWAY_URL}/orders",
        json={
            "customer_id": "cust_trace",
            "items": [{"product_id": "prod_001", "quantity": 1}],
            "amount": 150,
        },
    )
    assert response.status_code == 200, response.text

    trace_id = _wait_for_order_trace(http)
    trace_response = http.get(f"{TEMPO_URL}/api/traces/{trace_id}")
    assert trace_response.status_code == 200
    blob = trace_response.text.lower()
    for service in ("gateway", "orders", "inventory", "payments", "notifications"):
        assert service in blob


def test_payment_failure_increments_failed_orders(http: httpx.Client) -> None:
    before = _metrics_text(http, ORDERS_URL)
    before_failed = _parse_counter(before, "orders_failed_total")

    response = http.post(
        f"{GATEWAY_URL}/orders",
        json={
            "customer_id": "cust_obs_fail",
            "items": [{"product_id": "prod_001", "quantity": 1}],
            "amount": 99,
            "simulate_payment_failure": True,
        },
    )
    assert response.status_code == 402, response.text

    after = _metrics_text(http, ORDERS_URL)
    after_failed = _parse_counter(after, "orders_failed_total")
    assert after_failed > before_failed


def _parse_counter(metrics: str, name: str) -> float:
    for line in metrics.splitlines():
        if line.startswith(name) and not line.startswith(f"{name}_bucket"):
            parts = line.split()
            if len(parts) >= 2:
                return float(parts[-1])
    return 0.0
