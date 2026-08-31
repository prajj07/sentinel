from __future__ import annotations

import json
import logging

from aio_pika.abc import AbstractIncomingMessage

from app.routes.notifications import record_event
from sentinel_common.messaging import (
    QUEUE_ORDER_CREATED,
    amqp_headers_to_carrier,
    connect_rabbitmq,
    declare_topology,
)

logger = logging.getLogger(__name__)

_connection = None
_channel = None
_consumer_tag = None


async def handle_message(message: AbstractIncomingMessage) -> None:
    carrier = amqp_headers_to_carrier(message.headers)
    try:
        from sentinel_observability import start_consumer_span

        span_cm = start_consumer_span(
            "sentinel.notifications",
            "consume order.created",
            carrier,
        )
        with span_cm:
            async with message.process():
                payload = json.loads(message.body.decode("utf-8"))
                record_event(payload)
        return
    except ImportError:
        pass

    async with message.process():
        payload = json.loads(message.body.decode("utf-8"))
        record_event(payload)


async def start_consumer() -> None:
    global _connection, _channel, _consumer_tag
    _connection = await connect_rabbitmq()
    _channel = await _connection.channel()
    await _channel.set_qos(prefetch_count=10)
    await declare_topology(_channel)
    queue = await _channel.get_queue(QUEUE_ORDER_CREATED)
    _consumer_tag = await queue.consume(handle_message)
    logger.info("notifications consumer started on queue %s", QUEUE_ORDER_CREATED)


async def stop_consumer() -> None:
    global _connection, _channel, _consumer_tag
    if _channel is not None and _consumer_tag is not None:
        await _channel.cancel(_consumer_tag)
    if _connection is not None:
        await _connection.close()
    _connection = None
    _channel = None
    _consumer_tag = None
