"""Seed baseline inventory rows for local demos and integration tests."""

from __future__ import annotations

import os
import uuid

from sqlalchemy import select

from sentinel_common.db import get_session_factory
from sentinel_common.models import InventoryItem
from sentinel_common.redis_cache import invalidate_cached_inventory

SEED_ITEMS = [
    {"product_id": "prod_001", "available_quantity": 100},
    {"product_id": "prod_002", "available_quantity": 50},
]

RESET_THRESHOLD = int(os.getenv("INVENTORY_SEED_RESET_THRESHOLD", "80"))


def main() -> None:
    session = get_session_factory()()
    try:
        for item in SEED_ITEMS:
            existing = session.scalar(
                select(InventoryItem).where(InventoryItem.product_id == item["product_id"])
            )
            if existing is None:
                session.add(
                    InventoryItem(
                        id=uuid.uuid4(),
                        product_id=item["product_id"],
                        available_quantity=item["available_quantity"],
                    )
                )
            elif existing.available_quantity < RESET_THRESHOLD:
                existing.available_quantity = item["available_quantity"]
            invalidate_cached_inventory(item["product_id"])
        session.commit()
        print("Inventory seed complete")
    finally:
        session.close()


if __name__ == "__main__":
    main()
