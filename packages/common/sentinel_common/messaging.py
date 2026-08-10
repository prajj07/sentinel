from __future__ import annotations

import json
from typing import Any

import aio_pika
from aio_pika import ExchangeType, Message

from sentinel_common.settings import get_rabbitmq_settings

ROUTING_ORDER_CREATED = "order.created"
ROUTING_PAYMENT_COMPLETED = "payment.completed"
ROUTING_PAYMENT_FAILED = "payment.failed"

QUEUE_ORDER_CREATED = "order.created"
QUEUE_PAYMENT_COMPLETED = "payment.completed"
QUEUE_PAYMENT_FAILED = "payment.failed"


async def connect_rabbitmq(
    *,
    retries: int = 30,
    delay_seconds: float = 1.0,
) -> aio_pika.RobustConnection:
    """Connect to RabbitMQ with startup retries (broker can lag past healthcheck)."""
    import asyncio

    settings = get_rabbitmq_settings()
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            return await aio_pika.connect_robust(settings.rabbitmq_url)
        except Exception as exc:  # noqa: BLE001 - retry any connect failure at boot
            last_error = exc
            if attempt == retries:
                break
            await asyncio.sleep(delay_seconds)
    assert last_error is not None
    raise last_error


async def declare_topology(channel: aio_pika.Channel) -> aio_pika.Exchange:
    settings = get_rabbitmq_settings()
    exchange = await channel.declare_exchange(
        settings.rabbitmq_exchange,
        ExchangeType.TOPIC,
        durable=True,
    )

    for queue_name, routing_key in (
        (QUEUE_ORDER_CREATED, ROUTING_ORDER_CREATED),
        (QUEUE_PAYMENT_COMPLETED, ROUTING_PAYMENT_COMPLETED),
        (QUEUE_PAYMENT_FAILED, ROUTING_PAYMENT_FAILED),
    ):
        queue = await channel.declare_queue(queue_name, durable=True)
        await queue.bind(exchange, routing_key=routing_key)

    return exchange


async def publish_event(
    channel: aio_pika.Channel,
    exchange: aio_pika.Exchange,
    routing_key: str,
    payload: dict[str, Any],
) -> None:
    body = json.dumps(payload, default=str).encode("utf-8")
    message = Message(
        body=body,
        content_type="application/json",
        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
    )
    await exchange.publish(message, routing_key=routing_key)
