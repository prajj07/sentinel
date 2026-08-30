"""Add orders.payment_id FK to payments.id

Revision ID: 0002_orders_payment_id
Revises: 0001_initial
Create Date: 2026-08-10 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_orders_payment_id"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("payment_id", sa.Uuid(), nullable=True))
    op.create_index("ix_orders_payment_id", "orders", ["payment_id"])
    op.create_foreign_key(
        "fk_orders_payment_id",
        "orders",
        "payments",
        ["payment_id"],
        ["id"],
        ondelete="SET NULL",
    )
    # Backfill from existing successful payments (one per order)
    op.execute(
        """
        UPDATE orders AS o
        SET payment_id = p.id
        FROM (
            SELECT DISTINCT ON (order_id) id, order_id
            FROM payments
            WHERE status = 'SUCCESS'
            ORDER BY order_id, created_at DESC
        ) AS p
        WHERE p.order_id = o.id
          AND o.payment_id IS NULL
        """
    )


def downgrade() -> None:
    op.drop_constraint("fk_orders_payment_id", "orders", type_="foreignkey")
    op.drop_index("ix_orders_payment_id", table_name="orders")
    op.drop_column("orders", "payment_id")
