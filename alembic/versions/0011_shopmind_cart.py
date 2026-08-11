"""create isolated SKU-based ShopMind cart

Revision ID: 0011_shopmind_cart
Revises: 0010_pending_action_contract
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0011_shopmind_cart"
down_revision: Union[str, None] = "0010_pending_action_contract"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "shopmind_cart_items",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("sku_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("quantity >= 1", name="ck_shopmind_cart_items_quantity_positive"),
        sa.CheckConstraint("quantity <= 20", name="ck_shopmind_cart_items_quantity_max"),
        sa.CheckConstraint("version >= 1", name="ck_shopmind_cart_items_version_positive"),
        sa.ForeignKeyConstraint(
            ["sku_id"], ["shopmind_product_skus.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "sku_id", name="uq_shopmind_cart_items_user_sku"),
    )
    op.create_index(
        "idx_shopmind_cart_items_user_updated_at",
        "shopmind_cart_items",
        ["user_id", "updated_at"],
    )
    op.create_index("idx_shopmind_cart_items_sku", "shopmind_cart_items", ["sku_id"])


def downgrade() -> None:
    op.drop_index("idx_shopmind_cart_items_sku", table_name="shopmind_cart_items")
    op.drop_index("idx_shopmind_cart_items_user_updated_at", table_name="shopmind_cart_items")
    op.drop_table("shopmind_cart_items")
