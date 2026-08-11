"""add ShopMind SKU and inventory tables

Revision ID: 0009_shopmind_skus_inventory
Revises: 0008_shopmind_catalog_identity
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0009_shopmind_skus_inventory"
down_revision: Union[str, None] = "0008_shopmind_catalog_identity"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
JSON_TYPE = sa.JSON().with_variant(postgresql.JSONB, "postgresql")


def upgrade() -> None:
    op.create_table(
        "shopmind_product_skus",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("product_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("sku_code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("money_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("sale_status", sa.String(length=16), nullable=False),
        sa.Column("variant_attributes_json", JSON_TYPE, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("managed_by_seed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("seed_source", sa.String(length=64), nullable=True),
        sa.Column("seed_version", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("money_amount > 0", name="ck_shopmind_product_skus_money_positive"),
        sa.CheckConstraint("length(currency) = 3", name="ck_shopmind_product_skus_currency_length"),
        sa.CheckConstraint("currency = upper(currency)", name="ck_shopmind_product_skus_currency_upper"),
        sa.CheckConstraint("sale_status IN ('draft', 'active', 'inactive')", name="ck_shopmind_product_skus_sale_status"),
        sa.ForeignKeyConstraint(["product_id"], ["shopmind_products.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sku_code"),
    )
    op.create_table(
        "shopmind_inventory",
        sa.Column("sku_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("on_hand_quantity", sa.Integer(), nullable=False),
        sa.Column("reserved_quantity", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("on_hand_quantity >= 0", name="ck_shopmind_inventory_on_hand_nonnegative"),
        sa.CheckConstraint("reserved_quantity >= 0", name="ck_shopmind_inventory_reserved_nonnegative"),
        sa.CheckConstraint("reserved_quantity <= on_hand_quantity", name="ck_shopmind_inventory_reserved_lte_on_hand"),
        sa.CheckConstraint("version >= 0", name="ck_shopmind_inventory_version_nonnegative"),
        sa.ForeignKeyConstraint(["sku_id"], ["shopmind_product_skus.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("sku_id"),
    )
    op.create_index("idx_shopmind_product_skus_product_status", "shopmind_product_skus", ["product_id", "sale_status"])


def downgrade() -> None:
    op.drop_index("idx_shopmind_product_skus_product_status", table_name="shopmind_product_skus")
    op.drop_table("shopmind_inventory")
    op.drop_table("shopmind_product_skus")
