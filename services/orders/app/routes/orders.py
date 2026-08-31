from __future__ import annotations

import logging
import time
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sentinel_observability import ORDER_DURATION, ORDERS_CREATED, ORDERS_FAILED
from sqlalchemy.orm import Session

from app.config import get_settings
from sentinel_common.db import get_session
from sentinel_common.http_client import DownstreamError, DownstreamTimeoutError, request_json
from sentinel_common.messaging import (
    ROUTING_ORDER_CREATED,
    connect_rabbitmq,
    declare_topology,
    publish_event,
)
from sentinel_common.models import Order
from sentinel_contracts.orders import CreateOrderRequest, CreateOrderResponse

logger = logging.getLogger(__name__)
router = APIRouter()

_connection = None
_channel = None
_exchange = None


async def _ensure_publisher() -> None:
    global _connection, _channel, _exchange
    if _exchange is not None:
        return
    _connection = await connect_rabbitmq()
    _channel = await _connection.channel()
    _exchange = await declare_topology(_channel)


async def publish_order_created(payload: dict[str, Any]) -> None:
    await _ensure_publisher()
    assert _channel is not None and _exchange is not None
    await publish_event(_channel, _exchange, ROUTING_ORDER_CREATED, payload)


async def _release_reservations(
    *,
    inventory_url: str,
    timeout_seconds: float,
    order_id: UUID,
    reserved_items: list[tuple[str, int]],
    original_error: str | None,
) -> None:
    """Best-effort compensating release for items reserved earlier in this request."""
    if not reserved_items:
        return

    base = inventory_url.rstrip("/")
    for product_id, quantity in reserved_items:
        try:
            status, body = await request_json(
                "POST",
                f"{base}/inventory/release",
                json_body={"product_id": product_id, "quantity": quantity},
                timeout_seconds=timeout_seconds,
            )
            if status >= 400:
                logger.error(
                    "compensation_failed order_id=%s product_id=%s quantity=%s "
                    "original_payment_error=%s compensation_error=http_status=%s body=%s",
                    order_id,
                    product_id,
                    quantity,
                    original_error,
                    status,
                    body,
                )
            else:
                logger.info(
                    "compensation_released order_id=%s product_id=%s quantity=%s",
                    order_id,
                    product_id,
                    quantity,
                )
        except Exception as exc:
            logger.exception(
                "compensation_failed order_id=%s product_id=%s quantity=%s "
                "original_payment_error=%s compensation_error=%s",
                order_id,
                product_id,
                quantity,
                original_error,
                exc,
            )


def _mark_failed(session: Session, order: Order) -> Order:
    order.status = "failed"
    session.commit()
    session.refresh(order)
    return order


def _http_error_detail(exc: HTTPException) -> str:
    return str(exc.detail)


@router.post("/orders", response_model=CreateOrderResponse)
async def create_order(
    payload: CreateOrderRequest,
    session: Session = Depends(get_session),
) -> CreateOrderResponse:
    settings = get_settings()
    started = time.perf_counter()

    order = Order(
        customer_id=payload.customer_id,
        status="pending",
        amount=payload.amount,
    )
    session.add(order)
    session.commit()
    session.refresh(order)

    payment_id: UUID | None = None
    reserved_items: list[tuple[str, int]] = []
    payment_completed = False
    pending_error: HTTPException | None = None

    try:
        for item in payload.items:
            try:
                reserve_status, reserve_body = await request_json(
                    "POST",
                    f"{settings.inventory_url.rstrip('/')}/inventory/reserve",
                    json_body={"product_id": item.product_id, "quantity": item.quantity},
                    timeout_seconds=settings.http_timeout_seconds,
                )
            except DownstreamTimeoutError as exc:
                pending_error = HTTPException(status_code=504, detail=str(exc))
                break
            except DownstreamError as exc:
                pending_error = HTTPException(status_code=exc.status_code, detail=str(exc))
                break

            if reserve_status >= 400:
                pending_error = HTTPException(status_code=reserve_status, detail=reserve_body)
                break

            reserved_items.append((item.product_id, item.quantity))

        if pending_error is not None:
            raise pending_error

        order.status = "reserved"
        session.commit()

        payment_path = (
            "/payments/simulate-failure"
            if payload.simulate_payment_failure
            else "/payments"
        )
        try:
            pay_status, pay_body = await request_json(
                "POST",
                f"{settings.payments_url.rstrip('/')}{payment_path}",
                json_body={"order_id": str(order.id), "amount": payload.amount},
                timeout_seconds=settings.http_timeout_seconds,
            )
        except DownstreamTimeoutError as exc:
            raise HTTPException(status_code=504, detail=str(exc)) from exc
        except DownstreamError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Unexpected payment error: {exc}",
            ) from exc

        if pay_status >= 400:
            raise HTTPException(status_code=pay_status, detail=pay_body)

        if not isinstance(pay_body, dict) or pay_body.get("status") != "SUCCESS":
            raise HTTPException(
                status_code=402,
                detail={
                    "message": "Payment failed; inventory reservation released",
                    "payment": pay_body,
                },
            )

        payment_id = UUID(str(pay_body["id"]))
        payment_completed = True
        order.payment_id = payment_id
        order.status = "confirmed"
        session.commit()
        session.refresh(order)

        await publish_order_created(
            {
                "event": "order.created",
                "order_id": str(order.id),
                "customer_id": order.customer_id,
                "status": order.status,
                "amount": order.amount,
                "payment_id": str(payment_id),
                "items": [item.model_dump() for item in payload.items],
            }
        )
    except HTTPException as exc:
        pending_error = exc
    except Exception as exc:
        pending_error = HTTPException(
            status_code=502,
            detail=f"Order processing failed: {exc}",
        )
        logger.exception("unexpected_order_failure order_id=%s", order.id)
    finally:
        if reserved_items and not payment_completed:
            await _release_reservations(
                inventory_url=settings.inventory_url,
                timeout_seconds=settings.http_timeout_seconds,
                order_id=order.id,
                reserved_items=reserved_items,
                original_error=_http_error_detail(pending_error) if pending_error else None,
            )
            if order.status != "failed":
                _mark_failed(session, order)

    if pending_error is not None:
        ORDERS_FAILED.inc()
        ORDER_DURATION.observe(time.perf_counter() - started)
        raise pending_error

    ORDERS_CREATED.inc()
    ORDER_DURATION.observe(time.perf_counter() - started)
    return CreateOrderResponse(
        id=order.id,
        customer_id=order.customer_id,
        status=order.status,
        amount=order.amount,
        payment_id=order.payment_id,
        created_at=order.created_at,
    )
