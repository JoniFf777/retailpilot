"""Catalog ORM models kept separate from the legacy V2 Product model."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


CATALOG_JSON = JSON().with_variant(JSONB, "postgresql")


class SeedManagedMixin:
    managed_by_seed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    seed_source: Mapped[Optional[str]] = mapped_column(String(64))
    seed_version: Mapped[Optional[str]] = mapped_column(String(32))


class CatalogCategory(SeedManagedMixin, Base):
    __tablename__ = "shopmind_categories"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'inactive')", name="ck_shopmind_categories_status"),
        UniqueConstraint("parent_id", "code", name="uq_shopmind_categories_parent_code", postgresql_nulls_not_distinct=True),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    parent_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("shopmind_categories.id", ondelete="RESTRICT"))
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    parent: Mapped[Optional["CatalogCategory"]] = relationship(remote_side=[id])


class AttributeDefinition(SeedManagedMixin, Base):
    __tablename__ = "shopmind_attribute_definitions"
    __table_args__ = (
        CheckConstraint("scope IN ('spu', 'sku')", name="ck_shopmind_attribute_definitions_scope"),
        CheckConstraint("data_type IN ('string', 'integer', 'decimal', 'boolean', 'string_list')", name="ck_shopmind_attribute_definitions_data_type"),
        UniqueConstraint("category_id", "code", name="uq_shopmind_attribute_definitions_category_code"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    category_id: Mapped[UUID] = mapped_column(ForeignKey("shopmind_categories.id", ondelete="RESTRICT"), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    scope: Mapped[str] = mapped_column(String(8), nullable=False)
    data_type: Mapped[str] = mapped_column(String(16), nullable=False)
    unit: Mapped[Optional[str]] = mapped_column(String(32))
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    filterable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    searchable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    comparable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sku_dimension: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    options_json: Mapped[list[str]] = mapped_column(CATALOG_JSON, nullable=False, default=list)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class CatalogProduct(SeedManagedMixin, Base):
    __tablename__ = "shopmind_products"
    __table_args__ = (
        CheckConstraint("sale_status IN ('draft', 'active', 'inactive')", name="ck_shopmind_products_sale_status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    product_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    legacy_product_id: Mapped[Optional[str]] = mapped_column(String(64), unique=True)
    category_id: Mapped[UUID] = mapped_column(ForeignKey("shopmind_categories.id", ondelete="RESTRICT"), nullable=False)
    brand: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    sale_status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    attributes_json: Mapped[dict] = mapped_column(CATALOG_JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    category: Mapped[CatalogCategory] = relationship()
    skus: Mapped[list["CatalogSku"]] = relationship(back_populates="product")


class CatalogSku(SeedManagedMixin, Base):
    __tablename__ = "shopmind_product_skus"
    __table_args__ = (
        CheckConstraint("money_amount > 0", name="ck_shopmind_product_skus_money_positive"),
        CheckConstraint("length(currency) = 3", name="ck_shopmind_product_skus_currency_length"),
        CheckConstraint("currency = upper(currency)", name="ck_shopmind_product_skus_currency_upper"),
        CheckConstraint("sale_status IN ('draft', 'active', 'inactive')", name="ck_shopmind_product_skus_sale_status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    product_id: Mapped[UUID] = mapped_column(ForeignKey("shopmind_products.id", ondelete="RESTRICT"), nullable=False)
    sku_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    money_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    sale_status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    variant_attributes_json: Mapped[dict] = mapped_column(CATALOG_JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    product: Mapped[CatalogProduct] = relationship(back_populates="skus")
    inventory: Mapped[Optional["CatalogInventory"]] = relationship(back_populates="sku", uselist=False)


class CatalogInventory(Base):
    __tablename__ = "shopmind_inventory"
    __table_args__ = (
        CheckConstraint("on_hand_quantity >= 0", name="ck_shopmind_inventory_on_hand_nonnegative"),
        CheckConstraint("reserved_quantity >= 0", name="ck_shopmind_inventory_reserved_nonnegative"),
        CheckConstraint("reserved_quantity <= on_hand_quantity", name="ck_shopmind_inventory_reserved_lte_on_hand"),
        CheckConstraint("version >= 0", name="ck_shopmind_inventory_version_nonnegative"),
    )

    sku_id: Mapped[UUID] = mapped_column(ForeignKey("shopmind_product_skus.id", ondelete="RESTRICT"), primary_key=True)
    on_hand_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reserved_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    sku: Mapped[CatalogSku] = relationship(back_populates="inventory")
