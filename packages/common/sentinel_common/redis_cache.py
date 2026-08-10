from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

import redis

from sentinel_common.settings import get_redis_settings

INVENTORY_KEY_PREFIX = "inv:"


@lru_cache
def get_redis_client() -> redis.Redis:
    settings = get_redis_settings()
    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


def inventory_cache_key(product_id: str) -> str:
    return f"{INVENTORY_KEY_PREFIX}{product_id}"


def get_cached_inventory(product_id: str) -> dict[str, Any] | None:
    client = get_redis_client()
    raw = client.get(inventory_cache_key(product_id))
    if raw is None:
        return None
    return json.loads(raw)


def set_cached_inventory(product_id: str, payload: dict[str, Any]) -> None:
    settings = get_redis_settings()
    client = get_redis_client()
    client.setex(
        inventory_cache_key(product_id),
        settings.inventory_cache_ttl_seconds,
        json.dumps(payload),
    )


def invalidate_cached_inventory(product_id: str) -> None:
    client = get_redis_client()
    client.delete(inventory_cache_key(product_id))
