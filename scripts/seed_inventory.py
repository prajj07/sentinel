"""Seed baseline inventory rows for local demos and integration tests."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from sentinel_common.db import get_session_factory
from sentinel_common.models import InventoryItem

SEED_ITEMS = [
    {"product_id": "prod_001", "available_quantity": 100},
    {"product_id": "prod_002", "available_quantity": 50},
]


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
            else:
                # Keep stock usable for local demos after previous test runs
                if existing.available_quantity < 10:
                    existing.available_quantity = item["available_quantity"]
        session.commit()
        print("Inventory seed complete")
    finally:
        session.close()


if __name__ == "__main__":
    main()
