"""create structured business tables

Revision ID: 0001_structured_tables
Revises:
Create Date: 2026-06-25 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0001_structured_tables"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "customers",
        sa.Column("customer_id", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("phone", sa.String(), nullable=True),
        sa.Column("city", sa.String(), nullable=False),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column("segment", sa.String(), nullable=False),
        sa.CheckConstraint(
            "segment IN ('Consumer', 'Corporate', 'Home Office')",
            name="ck_customers_segment",
        ),
        sa.PrimaryKeyConstraint("customer_id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("idx_customers_email", "customers", ["email"])

    op.create_table(
        "products",
        sa.Column("product_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.Column("in_stock", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "category IN ('Laptops', 'Monitors', 'Keyboards', 'Audio', 'Accessories')",
            name="ck_products_category",
        ),
        sa.CheckConstraint("price > 0", name="ck_products_price_positive"),
        sa.PrimaryKeyConstraint("product_id"),
    )
    op.create_index("idx_products_category", "products", ["category"])
    op.create_index("idx_products_in_stock", "products", ["in_stock"])

    op.create_table(
        "orders",
        sa.Column("order_id", sa.String(), nullable=False),
        sa.Column("customer_id", sa.String(), nullable=False),
        sa.Column("order_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("shipped_date", sa.Date(), nullable=True),
        sa.Column("tracking_number", sa.String(), nullable=True),
        sa.Column("total_amount", sa.Numeric(10, 2), nullable=False),
        sa.CheckConstraint(
            "status IN ('Processing', 'Shipped', 'Delivered', 'Cancelled')",
            name="ck_orders_status",
        ),
        sa.CheckConstraint(
            "total_amount >= 0", name="ck_orders_total_amount_nonnegative"
        ),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.customer_id"]),
        sa.PrimaryKeyConstraint("order_id"),
    )
    op.create_index("idx_orders_customer", "orders", ["customer_id"])
    op.create_index("idx_orders_date", "orders", ["order_date"])
    op.create_index("idx_orders_status", "orders", ["status"])

    op.create_table(
        "order_items",
        sa.Column(
            "order_item_id", sa.BigInteger(), sa.Identity(), nullable=False
        ),
        sa.Column("order_id", sa.String(), nullable=False),
        sa.Column("product_id", sa.String(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("price_per_unit", sa.Numeric(10, 2), nullable=False),
        sa.CheckConstraint(
            "quantity > 0", name="ck_order_items_quantity_positive"
        ),
        sa.CheckConstraint(
            "price_per_unit > 0", name="ck_order_items_price_positive"
        ),
        sa.ForeignKeyConstraint(
            ["order_id"], ["orders.order_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.product_id"]),
        sa.PrimaryKeyConstraint("order_item_id"),
    )
    op.create_index("idx_order_items_order", "order_items", ["order_id"])
    op.create_index("idx_order_items_product", "order_items", ["product_id"])

    op.create_table(
        "user_preferences",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("preference_type", sa.String(), nullable=False),
        sa.Column("preference_value", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "preference_type IN ('budget', 'brand', 'avoid', 'usage', 'style', 'other')",
            name="ck_user_preferences_type",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_user_preferences_user", "user_preferences", ["user_id"]
    )

    op.create_table(
        "cart_items",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("product_id", sa.String(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("quantity > 0", name="ck_cart_items_quantity_positive"),
        sa.ForeignKeyConstraint(["product_id"], ["products.product_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_cart_items_user", "cart_items", ["user_id"])
    op.create_index("idx_cart_items_product", "cart_items", ["product_id"])

    op.create_table(
        "pending_actions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("thread_id", sa.String(), nullable=True),
        sa.Column("action_type", sa.String(), nullable=False),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'confirmed', 'cancelled')",
            name="ck_pending_actions_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_pending_actions_user_status",
        "pending_actions",
        ["user_id", "status"],
    )
    op.create_index("idx_pending_actions_thread", "pending_actions", ["thread_id"])


def downgrade() -> None:
    op.drop_index("idx_pending_actions_thread", table_name="pending_actions")
    op.drop_index("idx_pending_actions_user_status", table_name="pending_actions")
    op.drop_table("pending_actions")

    op.drop_index("idx_cart_items_product", table_name="cart_items")
    op.drop_index("idx_cart_items_user", table_name="cart_items")
    op.drop_table("cart_items")

    op.drop_index("idx_user_preferences_user", table_name="user_preferences")
    op.drop_table("user_preferences")

    op.drop_index("idx_order_items_product", table_name="order_items")
    op.drop_index("idx_order_items_order", table_name="order_items")
    op.drop_table("order_items")

    op.drop_index("idx_orders_status", table_name="orders")
    op.drop_index("idx_orders_date", table_name="orders")
    op.drop_index("idx_orders_customer", table_name="orders")
    op.drop_table("orders")

    op.drop_index("idx_products_in_stock", table_name="products")
    op.drop_index("idx_products_category", table_name="products")
    op.drop_table("products")

    op.drop_index("idx_customers_email", table_name="customers")
    op.drop_table("customers")
