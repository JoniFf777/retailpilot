"""add Phase 5A Mock Payment Attempts and consumed reservations

Revision ID: 0013_shopmind_payments
Revises: 0012_shopmind_orders
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0013_shopmind_payments"
down_revision: Union[str, None] = "0012_shopmind_orders"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("ck_shopmind_orders_status", "shopmind_orders", type_="check")
    op.create_check_constraint(
        "ck_shopmind_orders_status",
        "shopmind_orders",
        "status IN ('pending_payment', 'cancelled', 'paid')",
    )

    op.drop_constraint(
        "ck_shopmind_inventory_reservations_status",
        "shopmind_inventory_reservations",
        type_="check",
    )
    op.drop_constraint(
        "ck_shopmind_inventory_reservations_release_state",
        "shopmind_inventory_reservations",
        type_="check",
    )
    op.add_column(
        "shopmind_inventory_reservations",
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_shopmind_inventory_reservations_status",
        "shopmind_inventory_reservations",
        "status IN ('active', 'released', 'consumed')",
    )
    op.create_check_constraint(
        "ck_shopmind_inventory_reservations_release_state",
        "shopmind_inventory_reservations",
        "(status = 'active' AND released_at IS NULL AND consumed_at IS NULL) OR "
        "(status = 'released' AND released_at IS NOT NULL AND consumed_at IS NULL) OR "
        "(status = 'consumed' AND released_at IS NULL AND consumed_at IS NOT NULL)",
    )

    op.create_table(
        "shopmind_payment_attempts",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("order_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_payment_id", sa.String(length=128), nullable=True),
        sa.Column("provider_idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("failure_code", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("provider_result_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("provider IN ('mock')", name="ck_shopmind_payment_attempts_provider"),
        sa.CheckConstraint(
            "status IN ('processing', 'unknown', 'provider_succeeded', 'failed', 'succeeded')",
            name="ck_shopmind_payment_attempts_status",
        ),
        sa.CheckConstraint("amount > 0", name="ck_shopmind_payment_attempts_amount_positive"),
        sa.CheckConstraint(
            "length(currency) = 3 AND currency = upper(currency)",
            name="ck_shopmind_payment_attempts_currency",
        ),
        sa.CheckConstraint(
            "length(idempotency_key) BETWEEN 1 AND 128",
            name="ck_shopmind_payment_attempts_idempotency_key_length",
        ),
        sa.CheckConstraint(
            "length(provider_idempotency_key) BETWEEN 1 AND 128",
            name="ck_shopmind_payment_attempts_provider_key_length",
        ),
        sa.CheckConstraint(
            "length(request_hash) = 64",
            name="ck_shopmind_payment_attempts_request_hash_length",
        ),
        sa.CheckConstraint(
            "(status = 'processing' AND provider_result_at IS NULL AND completed_at IS NULL AND failure_code IS NULL) OR "
            "(status = 'unknown' AND provider_result_at IS NOT NULL AND completed_at IS NULL AND failure_code IS NOT NULL) OR "
            "(status = 'provider_succeeded' AND provider_result_at IS NOT NULL AND completed_at IS NULL AND failure_code IS NULL) OR "
            "(status = 'failed' AND provider_result_at IS NOT NULL AND completed_at IS NOT NULL AND failure_code IS NOT NULL) OR "
            "(status = 'succeeded' AND provider_result_at IS NOT NULL AND completed_at IS NOT NULL AND failure_code IS NULL)",
            name="ck_shopmind_payment_attempts_outcome_consistency",
        ),
        sa.ForeignKeyConstraint(
            ["order_id"], ["shopmind_orders.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "order_id", "idempotency_key",
            name="uq_shopmind_payment_attempts_user_order_key",
        ),
        sa.UniqueConstraint(
            "provider", "provider_idempotency_key",
            name="uq_shopmind_payment_attempts_provider_key",
        ),
    )
    op.create_index(
        "idx_shopmind_payment_attempts_order_created_at",
        "shopmind_payment_attempts",
        ["order_id", "created_at"],
    )
    op.create_index(
        "idx_shopmind_payment_attempts_user_created_at",
        "shopmind_payment_attempts",
        ["user_id", "created_at"],
    )
    op.create_index(
        "uq_shopmind_payment_attempts_order_active",
        "shopmind_payment_attempts",
        ["order_id"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('processing', 'unknown', 'provider_succeeded')"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_shopmind_payment_attempts_order_active",
        table_name="shopmind_payment_attempts",
    )
    op.drop_index(
        "idx_shopmind_payment_attempts_user_created_at",
        table_name="shopmind_payment_attempts",
    )
    op.drop_index(
        "idx_shopmind_payment_attempts_order_created_at",
        table_name="shopmind_payment_attempts",
    )
    op.drop_table("shopmind_payment_attempts")

    op.drop_constraint(
        "ck_shopmind_inventory_reservations_release_state",
        "shopmind_inventory_reservations",
        type_="check",
    )
    op.drop_constraint(
        "ck_shopmind_inventory_reservations_status",
        "shopmind_inventory_reservations",
        type_="check",
    )
    op.drop_column("shopmind_inventory_reservations", "consumed_at")
    op.create_check_constraint(
        "ck_shopmind_inventory_reservations_status",
        "shopmind_inventory_reservations",
        "status IN ('active', 'released')",
    )
    op.create_check_constraint(
        "ck_shopmind_inventory_reservations_release_state",
        "shopmind_inventory_reservations",
        "(status = 'active' AND released_at IS NULL) OR "
        "(status = 'released' AND released_at IS NOT NULL)",
    )

    op.drop_constraint("ck_shopmind_orders_status", "shopmind_orders", type_="check")
    op.create_check_constraint(
        "ck_shopmind_orders_status",
        "shopmind_orders",
        "status IN ('pending_payment', 'cancelled')",
    )
