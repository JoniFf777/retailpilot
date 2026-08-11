"""add ShopMind catalog identity tables

Revision ID: 0008_shopmind_catalog_identity
Revises: 0007_governance_audit
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0008_shopmind_catalog_identity"
down_revision: Union[str, None] = "0007_governance_audit"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSON_TYPE = sa.JSON().with_variant(postgresql.JSONB, "postgresql")


def upgrade() -> None:
    op.create_table(
        "shopmind_categories",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("parent_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("managed_by_seed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("seed_source", sa.String(length=64), nullable=True),
        sa.Column("seed_version", sa.String(length=32), nullable=True),
        sa.CheckConstraint("status IN ('active', 'inactive')", name="ck_shopmind_categories_status"),
        sa.ForeignKeyConstraint(["parent_id"], ["shopmind_categories.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("parent_id", "code", name="uq_shopmind_categories_parent_code", postgresql_nulls_not_distinct=True),
    )
    op.create_table(
        "shopmind_attribute_definitions",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("category_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("scope", sa.String(length=8), nullable=False),
        sa.Column("data_type", sa.String(length=16), nullable=False),
        sa.Column("unit", sa.String(length=32), nullable=True),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("filterable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("searchable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("comparable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sku_dimension", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("options_json", JSON_TYPE, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("managed_by_seed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("seed_source", sa.String(length=64), nullable=True),
        sa.Column("seed_version", sa.String(length=32), nullable=True),
        sa.CheckConstraint("scope IN ('spu', 'sku')", name="ck_shopmind_attribute_definitions_scope"),
        sa.CheckConstraint("data_type IN ('string', 'integer', 'decimal', 'boolean', 'string_list')", name="ck_shopmind_attribute_definitions_data_type"),
        sa.ForeignKeyConstraint(["category_id"], ["shopmind_categories.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("category_id", "code", name="uq_shopmind_attribute_definitions_category_code"),
    )
    op.create_table(
        "shopmind_products",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("product_code", sa.String(length=64), nullable=False),
        sa.Column("legacy_product_id", sa.String(length=64), nullable=True),
        sa.Column("category_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("brand", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sale_status", sa.String(length=16), nullable=False),
        sa.Column("attributes_json", JSON_TYPE, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("managed_by_seed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("seed_source", sa.String(length=64), nullable=True),
        sa.Column("seed_version", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("sale_status IN ('draft', 'active', 'inactive')", name="ck_shopmind_products_sale_status"),
        sa.ForeignKeyConstraint(["category_id"], ["shopmind_categories.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_code"),
        sa.UniqueConstraint("legacy_product_id"),
    )
    op.create_index("idx_shopmind_products_category_status", "shopmind_products", ["category_id", "sale_status"])


def downgrade() -> None:
    op.drop_index("idx_shopmind_products_category_status", table_name="shopmind_products")
    op.drop_table("shopmind_products")
    op.drop_table("shopmind_attribute_definitions")
    op.drop_table("shopmind_categories")
