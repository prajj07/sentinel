"""Sentinel observability — OpenTelemetry traces and Prometheus metrics."""

from sentinel_observability.metrics import (
    INVENTORY_RELEASES,
    INVENTORY_RESERVATION_FAILURES,
    INVENTORY_RESERVATIONS,
    ORDER_DURATION,
    ORDERS_CREATED,
    ORDERS_FAILED,
    PAYMENT_DURATION,
    PAYMENTS_FAILED,
    PAYMENTS_TOTAL,
)
from sentinel_observability.setup import configure_observability
from sentinel_observability.tracing import (
    get_tracer,
    inject_trace_context,
    instrument_sqlalchemy,
    start_consumer_span,
)

__all__ = [
    "configure_observability",
    "get_tracer",
    "inject_trace_context",
    "instrument_sqlalchemy",
    "start_consumer_span",
    "ORDERS_CREATED",
    "ORDERS_FAILED",
    "ORDER_DURATION",
    "PAYMENTS_TOTAL",
    "PAYMENTS_FAILED",
    "PAYMENT_DURATION",
    "INVENTORY_RESERVATIONS",
    "INVENTORY_RELEASES",
    "INVENTORY_RESERVATION_FAILURES",
]
