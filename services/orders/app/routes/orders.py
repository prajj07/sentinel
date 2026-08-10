from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
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


@router.post("/orders", response_model=CreateOrderResponse)
async def create_order(
    payload: CreateOrderRequest,
    session: Session = Depends(get_session),
) -> CreateOrderResponse:
    settings = get_settings()

    order = Order(
        customer_id=payload.customer_id,
        status="pending",
        amount=payload.amount,
    )
    session.add(order)
    session.commit()
    session.refresh(order)

    payment_id: UUID | None = None

    try:
        for item in payload.items:
            reserve_status, reserve_body = await request_json(
                "POST",
                f"{settings.inventory_url.rstrip('/')}/inventory/reserve",
                json_body={"product_id": item.product_id, "quantity": item.quantity},
                timeout_seconds=settings.http_timeout_seconds,
            )
            if reserve_status >= 400:
                order.status = "failed"
                session.commit()
                session.refresh(order)
                raise HTTPException(status_code=reserve_status, detail=reserve_body)

        order.status = "reserved"
        session.commit()

        pay_status, pay_body = await request_json(
            "POST",
            f"{settings.payments_url.rstrip('/')}/payments",
            json_body={"order_id": str(order.id), "amount": payload.amount},
            timeout_seconds=settings.http_timeout_seconds,
        )
        if pay_status >= 400:
            order.status = "failed"
            session.commit()
            session.refresh(order)
            raise HTTPException(status_code=pay_status, detail=pay_body)

        if not isinstance(pay_body, dict) or pay_body.get("status") != "SUCCESS":
            order.status = "failed"
            session.commit()
            session.refresh(order)
            raise HTTPException(status_code=502, detail=pay_body)

        payment_id = UUID(str(pay_body["id"]))
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
    except DownstreamTimeoutError as exc:
        order.status = "failed"
        session.commit()
        session.refresh(order)
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except DownstreamError as exc:
        order.status = "failed"
        session.commit()
        session.refresh(order)
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return CreateOrderResponse(
        id=order.id,
        customer_id=order.customer_id,
        status=order.status,
        amount=order.amount,
        payment_id=payment_id,
        created_at=order.created_at,
    )
