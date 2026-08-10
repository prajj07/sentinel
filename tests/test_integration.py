import os
import time

import httpx
import pytest
import redis

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8000")
ORDERS_URL = os.getenv("ORDERS_URL", "http://localhost:8001")
INVENTORY_URL = os.getenv("INVENTORY_URL", "http://localhost:8002")
PAYMENTS_URL = os.getenv("PAYMENTS_URL", "http://localhost:8003")
NOTIFICATIONS_URL = os.getenv("NOTIFICATIONS_URL", "http://localhost:8004")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

TIMEOUT = httpx.Timeout(10.0)


@pytest.fixture(scope="session")
def http() -> httpx.Client:
    with httpx.Client(timeout=TIMEOUT) as client:
        yield client


def wait_for_notification(http: httpx.Client, order_id: str, timeout: float = 15.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = http.get(f"{NOTIFICATIONS_URL}/notifications/received")
        response.raise_for_status()
        body = response.json()
        for event in body.get("events", []):
            if event.get("order_id") == order_id:
                return event
        time.sleep(0.5)
    raise AssertionError(f"order.created notification not received for {order_id}")


def test_health_endpoints(http: httpx.Client) -> None:
    for base, name in (
        (GATEWAY_URL, "gateway"),
        (ORDERS_URL, "orders"),
        (INVENTORY_URL, "inventory"),
        (PAYMENTS_URL, "payments"),
        (NOTIFICATIONS_URL, "notifications"),
    ):
        response = http.get(f"{base}/health")
        assert response.status_code == 200
        body = response.json()
        assert body["service"] == name
        assert body["status"] == "healthy"


def test_inventory_cache_miss_then_hit(http: httpx.Client) -> None:
    product_id = "prod_001"
    client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    client.delete(f"inv:{product_id}")

    miss = http.get(f"{INVENTORY_URL}/inventory/{product_id}")
    assert miss.status_code == 200
    miss_body = miss.json()
    assert miss_body["cache_hit"] is False
    assert miss_body["product_id"] == product_id

    hit = http.get(f"{INVENTORY_URL}/inventory/{product_id}")
    assert hit.status_code == 200
    hit_body = hit.json()
    assert hit_body["cache_hit"] is True
    assert hit_body["available_quantity"] == miss_body["available_quantity"]


def test_inventory_reserve_and_oversell(http: httpx.Client) -> None:
    product_id = "prod_002"
    current = http.get(f"{INVENTORY_URL}/inventory/{product_id}")
    assert current.status_code == 200
    available = current.json()["available_quantity"]

    ok = http.post(
        f"{INVENTORY_URL}/inventory/reserve",
        json={"product_id": product_id, "quantity": 1},
    )
    assert ok.status_code == 200
    assert ok.json()["available_quantity"] == available - 1

    fail = http.post(
        f"{INVENTORY_URL}/inventory/reserve",
        json={"product_id": product_id, "quantity": available + 1000},
    )
    assert fail.status_code == 409


def test_payment_success_and_simulate_failure(http: httpx.Client) -> None:
    # Create a real order row via orders service happy path first pieces:
    # Use a tiny order so we get an order_id, then create an additional payment row
    # via simulate-failure against that order.
    create = http.post(
        f"{GATEWAY_URL}/orders",
        json={
            "customer_id": "cust_test_pay",
            "items": [{"product_id": "prod_001", "quantity": 1}],
            "amount": 100,
        },
    )
    assert create.status_code == 200, create.text
    order_id = create.json()["id"]

    success = http.post(
        f"{PAYMENTS_URL}/payments",
        json={"order_id": order_id, "amount": 50},
    )
    assert success.status_code == 200
    assert success.json()["status"] == "SUCCESS"

    failed = http.post(
        f"{PAYMENTS_URL}/payments/simulate-failure",
        json={"order_id": order_id, "amount": 50},
    )
    assert failed.status_code == 200
    assert failed.json()["status"] == "FAILED"


def test_order_creation_flow_and_rabbitmq(http: httpx.Client) -> None:
    http.delete(f"{NOTIFICATIONS_URL}/notifications/received")

    response = http.post(
        f"{GATEWAY_URL}/orders",
        json={
            "customer_id": "cust_001",
            "items": [{"product_id": "prod_001", "quantity": 2}],
            "amount": 1499,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "confirmed"
    assert body["payment_id"] is not None
    assert body["customer_id"] == "cust_001"

    event = wait_for_notification(http, body["id"])
    assert event["event"] == "order.created"
    assert event["status"] == "confirmed"
