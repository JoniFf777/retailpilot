"""create Phase 4A pending-payment Orders and inventory reservations

Revision ID: 0012_shopmind_orders
Revises: 0011_shopmind_cart
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0012_shopmind_orders"
down_revision: Union[str, None] = "0011_shopmind_cart"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "shopmind_orders",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("subtotal_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("total_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("checkout_cart_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('pending_payment', 'cancelled')", name="ck_shopmind_orders_status"),
        sa.CheckConstraint("length(currency) = 3", name="ck_shopmind_orders_currency_length"),
        sa.CheckConstraint("currency = upper(currency)", name="ck_shopmind_orders_currency_upper"),
        sa.CheckConstraint("subtotal_amount >= 0", name="ck_shopmind_orders_subtotal_nonnegative"),
        sa.CheckConstraint("total_amount >= 0", name="ck_shopmind_orders_total_nonnegative"),
        sa.CheckConstraint("total_amount = subtotal_amount", name="ck_shopmind_orders_total_equals_subtotal"),
        sa.CheckConstraint("version >= 1", name="ck_shopmind_orders_version_positive"),
        sa.CheckConstraint("length(checkout_cart_fingerprint) = 64", name="ck_shopmind_orders_cart_fingerprint_length"),
        sa.CheckConstraint("length(request_hash) = 64", name="ck_shopmind_orders_request_hash_length"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_shopmind_orders_user_idempotency"),
    )
    op.create_index("idx_shopmind_orders_user_created_at_id", "shopmind_orders", ["user_id", "created_at", "id"])
    op.create_index("idx_shopmind_orders_user_status_created_at", "shopmind_orders", ["user_id", "status", "created_at"])
    op.create_table(
        "shopmind_order_items",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("order_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("sku_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("product_code_snapshot", sa.String(length=64), nullable=False),
        sa.Column("product_name_snapshot", sa.String(length=255), nullable=False),
        sa.Column("sku_code_snapshot", sa.String(length=64), nullable=False),
        sa.Column("sku_name_snapshot", sa.String(length=255), nullable=False),
        sa.Column("unit_price_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("line_total_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("unit_price_amount > 0", name="ck_shopmind_order_items_unit_price_positive"),
        sa.CheckConstraint("quantity >= 1 AND quantity <= 20", name="ck_shopmind_order_items_quantity_bounds"),
        sa.CheckConstraint("line_total_amount > 0", name="ck_shopmind_order_items_line_total_positive"),
        sa.CheckConstraint("line_total_amount = unit_price_amount * quantity", name="ck_shopmind_order_items_line_total_matches"),
        sa.CheckConstraint("length(currency) = 3", name="ck_shopmind_order_items_currency_length"),
        sa.CheckConstraint("currency = upper(currency)", name="ck_shopmind_order_items_currency_upper"),
        sa.ForeignKeyConstraint(["order_id"], ["shopmind_orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sku_id"], ["shopmind_product_skus.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id", "sku_id", name="uq_shopmind_order_items_order_sku"),
    )
    op.create_table(
        "shopmind_inventory_reservations",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("order_item_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("sku_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("quantity >= 1 AND quantity <= 20", name="ck_shopmind_inventory_reservations_quantity_bounds"),
        sa.CheckConstraint("status IN ('active', 'released')", name="ck_shopmind_inventory_reservations_status"),
        sa.CheckConstraint("(status = 'active' AND released_at IS NULL) OR (status = 'released' AND released_at IS NOT NULL)", name="ck_shopmind_inventory_reservations_release_state"),
        sa.ForeignKeyConstraint(["order_item_id"], ["shopmind_order_items.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["sku_id"], ["shopmind_product_skus.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_item_id", name="uq_shopmind_inventory_reservations_order_item"),
    )
    op.create_index("idx_shopmind_inventory_reservations_sku_status", "shopmind_inventory_reservations", ["sku_id", "status"])


def downgrade() -> None:
    op.drop_index("idx_shopmind_inventory_reservations_sku_status", table_name="shopmind_inventory_reservations")
    op.drop_table("shopmind_inventory_reservations")
    op.drop_table("shopmind_order_items")
    op.drop_index("idx_shopmind_orders_user_status_created_at", table_name="shopmind_orders")
    op.drop_index("idx_shopmind_orders_user_created_at_id", table_name="shopmind_orders")
    op.drop_table("shopmind_orders")
