"""Compensation / inventory release coverage for the order creation flow."""

from __future__ import annotations

import asyncio
import logging
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import pytest

GATEWAY_URL = "http://localhost:8000"
INVENTORY_URL = "http://localhost:8002"
PAYMENTS_HEALTH = "http://localhost:8003/health"
TIMEOUT = httpx.Timeout(10.0)

# Allow importing Orders app modules for logging unit tests
_ORDERS_APP_ROOT = Path(__file__).resolve().parents[1] / "services" / "orders"
if str(_ORDERS_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_ORDERS_APP_ROOT))


@pytest.fixture
def http() -> httpx.Client:
    with httpx.Client(timeout=TIMEOUT) as client:
        yield client


def _inventory_qty(http: httpx.Client, product_id: str) -> int:
    response = http.get(f"{INVENTORY_URL}/inventory/{product_id}")
    assert response.status_code == 200
    return response.json()["available_quantity"]


def _wait_healthy(http: httpx.Client, url: str, timeout: float = 60.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            response = http.get(url)
            if response.status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(1)
    raise AssertionError(f"service not healthy: {url}")


def test_payment_success_decreases_inventory(http: httpx.Client) -> None:
    product_id = "prod_001"
    before = _inventory_qty(http, product_id)

    response = http.post(
        f"{GATEWAY_URL}/orders",
        json={
            "customer_id": "cust_success_inv",
            "items": [{"product_id": product_id, "quantity": 2}],
            "amount": 200,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "confirmed"
    assert _inventory_qty(http, product_id) == before - 2


def test_payment_failure_restores_inventory(http: httpx.Client) -> None:
    product_id = "prod_001"
    before = _inventory_qty(http, product_id)

    response = http.post(
        f"{GATEWAY_URL}/orders",
        json={
            "customer_id": "cust_fail_restore",
            "items": [{"product_id": product_id, "quantity": 3}],
            "amount": 300,
            "simulate_payment_failure": True,
        },
    )
    assert response.status_code == 402, response.text
    assert "Payment failed" in response.json()["detail"]["message"]
    assert _inventory_qty(http, product_id) == before


def test_payment_unavailable_restores_inventory(http: httpx.Client) -> None:
    product_id = "prod_001"
    before = _inventory_qty(http, product_id)

    subprocess.run(["docker", "compose", "stop", "payments"], check=True)
    try:
        response = http.post(
            f"{GATEWAY_URL}/orders",
            json={
                "customer_id": "cust_pay_down",
                "items": [{"product_id": product_id, "quantity": 1}],
                "amount": 50,
            },
        )
        assert response.status_code == 502, response.text
        assert _inventory_qty(http, product_id) == before
    finally:
        subprocess.run(["docker", "compose", "start", "payments"], check=True)
        _wait_healthy(http, PAYMENTS_HEALTH)


def test_multi_item_payment_failure_releases_all(http: httpx.Client) -> None:
    before_001 = _inventory_qty(http, "prod_001")
    before_002 = _inventory_qty(http, "prod_002")

    response = http.post(
        f"{GATEWAY_URL}/orders",
        json={
            "customer_id": "cust_multi_fail",
            "items": [
                {"product_id": "prod_001", "quantity": 1},
                {"product_id": "prod_002", "quantity": 2},
            ],
            "amount": 400,
            "simulate_payment_failure": True,
        },
    )
    assert response.status_code == 402, response.text
    assert _inventory_qty(http, "prod_001") == before_001
    assert _inventory_qty(http, "prod_002") == before_002


def test_reservation_failure_does_not_release_unreserved_item(http: httpx.Client) -> None:
    before_001 = _inventory_qty(http, "prod_001")
    before_002 = _inventory_qty(http, "prod_002")

    response = http.post(
        f"{GATEWAY_URL}/orders",
        json={
            "customer_id": "cust_partial_reserve",
            "items": [
                {"product_id": "prod_001", "quantity": 1},
                {"product_id": "prod_does_not_exist", "quantity": 1},
            ],
            "amount": 100,
        },
    )
    assert response.status_code == 404, response.text
    assert _inventory_qty(http, "prod_001") == before_001
    assert _inventory_qty(http, "prod_002") == before_002


def test_compensation_failure_is_logged_and_does_not_hide_payment_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    try:
        from app.routes import orders as orders_routes
    except ImportError as exc:
        pytest.skip(f"orders app not importable on host: {exc}")

    order_id = uuid4()
    original = "Downstream request failed: Connection refused"

    with caplog.at_level(logging.ERROR):
        with patch(
            "app.routes.orders.request_json",
            new_callable=AsyncMock,
            side_effect=Exception("inventory release boom"),
        ):
            asyncio.run(
                orders_routes._release_reservations(
                    inventory_url="http://inventory:8002",
                    timeout_seconds=1.0,
                    order_id=order_id,
                    reserved_items=[("prod_001", 2)],
                    original_error=original,
                )
            )

    joined = "\n".join(record.getMessage() for record in caplog.records)
    assert "compensation_failed" in joined
    assert str(order_id) in joined
    assert "prod_001" in joined
    assert "quantity=2" in joined or "2" in joined
    assert original in joined
    assert "inventory release boom" in joined
