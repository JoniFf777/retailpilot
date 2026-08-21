"""add persisted Order payment deadlines and expiration support

Revision ID: 0015_shopmind_order_expiration
Revises: 0014_shopmind_outbox_events
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0015_shopmind_order_expiration"
down_revision: Union[str, None] = "0014_shopmind_outbox_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


DEFAULT_ORDER_PAYMENT_TTL_SECONDS = 1_800


def upgrade() -> None:
    op.add_column(
        "shopmind_orders",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.drop_constraint("ck_shopmind_orders_status", "shopmind_orders", type_="check")
    op.create_check_constraint(
        "ck_shopmind_orders_status",
        "shopmind_orders",
        "status IN ('pending_payment', 'cancelled', 'paid', 'expired')",
    )
    op.execute(
        sa.text(
            "UPDATE shopmind_orders "
            "SET expires_at = created_at + INTERVAL '1800 seconds' "
            "WHERE status = 'pending_payment' AND expires_at IS NULL"
        )
    )
    op.create_check_constraint(
        "ck_shopmind_orders_expiration_deadline",
        "shopmind_orders",
        "status IN ('paid', 'cancelled') OR expires_at IS NOT NULL",
    )
    op.create_index(
        "idx_shopmind_orders_expiration",
        "shopmind_orders",
        ["status", "expires_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("idx_shopmind_orders_expiration", table_name="shopmind_orders")
    op.drop_constraint(
        "ck_shopmind_orders_expiration_deadline", "shopmind_orders", type_="check"
    )
    op.drop_constraint("ck_shopmind_orders_status", "shopmind_orders", type_="check")
    op.create_check_constraint(
        "ck_shopmind_orders_status",
        "shopmind_orders",
        "status IN ('pending_payment', 'cancelled', 'paid')",
    )
    op.drop_column("shopmind_orders", "expires_at")
