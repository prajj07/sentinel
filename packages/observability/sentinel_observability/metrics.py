from __future__ import annotations

import time

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.requests import Request
from starlette.responses import Response

# HTTP (all services)
HTTP_REQUESTS = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "handler", "status"],
)
HTTP_REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency",
    ["method", "handler"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

# Orders
ORDERS_CREATED = Counter(
    "orders_created_total",
    "Total number of orders successfully confirmed",
)
ORDERS_FAILED = Counter(
    "orders_failed_total",
    "Total number of orders that failed",
)
ORDER_DURATION = Histogram(
    "order_duration_seconds",
    "Time spent processing order creation",
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

# Payments
PAYMENTS_TOTAL = Counter(
    "payments_total",
    "Total number of payment attempts",
    ["status"],
)
PAYMENTS_FAILED = Counter(
    "payments_failed_total",
    "Total number of failed payments",
)
PAYMENT_DURATION = Histogram(
    "payment_duration_seconds",
    "Time spent processing payments",
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

# Inventory
INVENTORY_RESERVATIONS = Counter(
    "inventory_reservations_total",
    "Total successful inventory reservations",
)
INVENTORY_RELEASES = Counter(
    "inventory_releases_total",
    "Total inventory releases (compensation)",
)
INVENTORY_RESERVATION_FAILURES = Counter(
    "inventory_reservation_failures_total",
    "Total failed inventory reservation attempts",
)


def _resolve_handler(request: Request) -> str:
    route = request.scope.get("route")
    if route is not None and hasattr(route, "path"):
        return route.path
    return request.url.path


async def prometheus_middleware(request: Request, call_next):
    if request.url.path == "/metrics":
        return await call_next(request)

    started = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - started
    handler = _resolve_handler(request)

    HTTP_REQUESTS.labels(request.method, handler, str(response.status_code)).inc()
    HTTP_REQUEST_DURATION.labels(request.method, handler).observe(duration)
    return response


async def metrics_endpoint(_: Request) -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


def mount_metrics(app) -> None:
    app.middleware("http")(prometheus_middleware)
    app.add_route("/metrics", metrics_endpoint, include_in_schema=False)
