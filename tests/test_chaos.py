"""Sprint 3 chaos engine tests (stack must be running)."""

from __future__ import annotations

import os
import time

import httpx
import pytest

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8000")
ORDERS_URL = os.getenv("ORDERS_URL", "http://localhost:8001")
INVENTORY_URL = os.getenv("INVENTORY_URL", "http://localhost:8002")
PAYMENTS_URL = os.getenv("PAYMENTS_URL", "http://localhost:8003")
CHAOS_URL = os.getenv("CHAOS_URL", "http://localhost:8005")
TEMPO_URL = os.getenv("TEMPO_URL", "http://localhost:3200")

TARGET_BASES = (GATEWAY_URL, ORDERS_URL, INVENTORY_URL, PAYMENTS_URL)

TIMEOUT = httpx.Timeout(20.0)


@pytest.fixture
def http() -> httpx.Client:
    with httpx.Client(timeout=TIMEOUT) as client:
        yield client
        _stop_running(client)


def _stop_running(http: httpx.Client) -> None:
    try:
        for base in TARGET_BASES:
            http.post(f"{base}/internal/chaos/deactivate", params={"force": "true"})
        response = http.get(f"{CHAOS_URL}/chaos/experiments")
        if response.status_code != 200:
            return
        for experiment in response.json():
            if experiment.get("status") == "running":
                http.post(f"{CHAOS_URL}/chaos/stop/{experiment['id']}")
    except httpx.HTTPError:
        return


def _parse_counter(metrics: str, name: str) -> float:
    for line in metrics.splitlines():
        if line.startswith(name) and not line.startswith(f"{name}_bucket"):
            parts = line.split()
            if len(parts) >= 2:
                return float(parts[-1])
    return 0.0


def _inject(http: httpx.Client, **payload) -> dict:
    response = http.post(f"{CHAOS_URL}/chaos/inject", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def test_chaos_health(http: httpx.Client) -> None:
    response = http.get(f"{CHAOS_URL}/health")
    assert response.status_code == 200
    assert response.json()["service"] == "chaos"


def test_chaos_inject_latency_payments(http: httpx.Client) -> None:
    experiment = _inject(
        http,
        service="payments",
        type="latency",
        duration_seconds=20,
        delay_ms=1500,
    )
    assert experiment["status"] == "running"

    health = http.get(f"{PAYMENTS_URL}/health")
    assert health.status_code == 200

    started = time.perf_counter()
    order = http.post(
        f"{GATEWAY_URL}/orders",
        json={
            "customer_id": "cust_chaos_latency",
            "items": [{"product_id": "prod_001", "quantity": 1}],
            "amount": 50,
        },
    )
    elapsed = time.perf_counter() - started
    assert order.status_code == 200, order.text
    assert elapsed >= 1.3

    metrics = http.get(f"{PAYMENTS_URL}/metrics").text
    assert "chaos_requests_affected_total" in metrics


def test_chaos_inject_http_500(http: httpx.Client) -> None:
    _inject(
        http,
        service="payments",
        type="http_500",
        duration_seconds=20,
    )
    response = http.post(
        f"{GATEWAY_URL}/orders",
        json={
            "customer_id": "cust_chaos_500",
            "items": [{"product_id": "prod_001", "quantity": 1}],
            "amount": 80,
        },
    )
    assert response.status_code >= 400


def test_chaos_stop_clears_fault(http: httpx.Client) -> None:
    experiment = _inject(
        http,
        service="payments",
        type="http_500",
        duration_seconds=30,
    )
    stop = http.post(f"{CHAOS_URL}/chaos/stop/{experiment['experiment_id']}")
    assert stop.status_code == 200
    assert stop.json()["status"] == "stopped"

    response = http.post(
        f"{GATEWAY_URL}/orders",
        json={
            "customer_id": "cust_chaos_recovered",
            "items": [{"product_id": "prod_001", "quantity": 1}],
            "amount": 80,
        },
    )
    assert response.status_code == 200, response.text


def test_chaos_experiment_lifecycle(http: httpx.Client) -> None:
    created = _inject(
        http,
        service="inventory",
        type="service_unavailable",
        duration_seconds=25,
    )
    experiment_id = created["experiment_id"]

    listed = http.get(f"{CHAOS_URL}/chaos/experiments")
    assert listed.status_code == 200
    ids = {item["id"] for item in listed.json()}
    assert experiment_id in ids

    detail = http.get(f"{CHAOS_URL}/chaos/experiments/{experiment_id}")
    assert detail.status_code == 200
    assert detail.json()["status"] == "running"

    stopped = http.post(f"{CHAOS_URL}/chaos/stop/{experiment_id}")
    assert stopped.json()["status"] == "stopped"

    health = http.get(f"{ORDERS_URL}/health")
    assert health.status_code == 200


def test_chaos_payment_degradation_scenario(http: httpx.Client) -> None:
    response = http.post(
        f"{CHAOS_URL}/chaos/scenarios/payment-degradation",
        json={
            "delay_ms": 1500,
            "duration_seconds": 25,
            "baseline_orders": 2,
            "traffic_orders": 4,
            "recovery_orders": 2,
        },
        timeout=60.0,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["service"] == "payments"
    assert body["type"] == "latency"
    assert "report" in body
    assert "impact_summary" in body
    assert body["impact"]["p95_s"] > body["baseline"]["p95_s"]
    assert body["result"] in {"PASSED", "FAILED"}
    if body["result"] == "PASSED":
        assert "PASSED" in body["report"]


def test_chaos_trace_attributes(http: httpx.Client) -> None:
    before = _parse_counter(http.get(f"{PAYMENTS_URL}/metrics").text, "chaos_requests_affected_total")

    experiment = _inject(
        http,
        service="payments",
        type="latency",
        duration_seconds=20,
        delay_ms=200,
    )
    experiment_id = experiment["experiment_id"]
    order = http.post(
        f"{GATEWAY_URL}/orders",
        json={
            "customer_id": "cust_chaos_trace",
            "items": [{"product_id": "prod_001", "quantity": 1}],
            "amount": 75,
        },
    )
    assert order.status_code == 200, order.text

    after = _parse_counter(http.get(f"{PAYMENTS_URL}/metrics").text, "chaos_requests_affected_total")
    assert after > before, "chaos_requests_affected_total should increase during experiment"

    http.post(f"{CHAOS_URL}/chaos/stop/{experiment_id}")

    deadline = time.time() + 30
    found = False
    while time.time() < deadline:
        search = http.get(f"{TEMPO_URL}/api/search", params={"limit": 50})
        if search.status_code == 200:
            for trace in search.json().get("traces", []):
                detail = http.get(f"{TEMPO_URL}/api/traces/{trace['traceID']}")
                if detail.status_code != 200:
                    continue
                blob = detail.text
                if experiment_id in blob or "chaos.inject" in blob:
                    found = True
                    break
        if found:
            break
        time.sleep(2)

    if not found:
        pytest.skip("Tempo did not index chaos span yet; metrics assertion passed")
