"""ORM models for pending-payment Orders and inventory reservations."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.catalog import models as _catalog_models  # noqa: F401
from app.db.base import Base


class ShopMindOrder(Base):
    __tablename__ = "shopmind_orders"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending_payment', 'cancelled', 'paid')",
            name="ck_shopmind_orders_status",
        ),
        CheckConstraint("length(currency) = 3", name="ck_shopmind_orders_currency_length"),
        CheckConstraint("currency = upper(currency)", name="ck_shopmind_orders_currency_upper"),
        CheckConstraint("subtotal_amount >= 0", name="ck_shopmind_orders_subtotal_nonnegative"),
        CheckConstraint("total_amount >= 0", name="ck_shopmind_orders_total_nonnegative"),
        CheckConstraint("total_amount = subtotal_amount", name="ck_shopmind_orders_total_equals_subtotal"),
        CheckConstraint("version >= 1", name="ck_shopmind_orders_version_positive"),
        CheckConstraint("length(checkout_cart_fingerprint) = 64", name="ck_shopmind_orders_cart_fingerprint_length"),
        CheckConstraint("length(request_hash) = 64", name="ck_shopmind_orders_request_hash_length"),
        UniqueConstraint("user_id", "idempotency_key", name="uq_shopmind_orders_user_idempotency"),
        Index("idx_shopmind_orders_user_created_at_id", "user_id", "created_at", "id"),
        Index("idx_shopmind_orders_user_status_created_at", "user_id", "status", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending_payment")
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    subtotal_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    checkout_cart_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    items: Mapped[list["ShopMindOrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan", order_by="ShopMindOrderItem.id"
    )


class ShopMindOrderItem(Base):
    __tablename__ = "shopmind_order_items"
    __table_args__ = (
        CheckConstraint("unit_price_amount > 0", name="ck_shopmind_order_items_unit_price_positive"),
        CheckConstraint("quantity >= 1 AND quantity <= 20", name="ck_shopmind_order_items_quantity_bounds"),
        CheckConstraint("line_total_amount > 0", name="ck_shopmind_order_items_line_total_positive"),
        CheckConstraint("line_total_amount = unit_price_amount * quantity", name="ck_shopmind_order_items_line_total_matches"),
        CheckConstraint("length(currency) = 3", name="ck_shopmind_order_items_currency_length"),
        CheckConstraint("currency = upper(currency)", name="ck_shopmind_order_items_currency_upper"),
        UniqueConstraint("order_id", "sku_id", name="uq_shopmind_order_items_order_sku"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    order_id: Mapped[UUID] = mapped_column(
        ForeignKey("shopmind_orders.id", ondelete="CASCADE"), nullable=False
    )
    sku_id: Mapped[UUID] = mapped_column(
        ForeignKey("shopmind_product_skus.id", ondelete="RESTRICT"), nullable=False
    )
    product_code_snapshot: Mapped[str] = mapped_column(String(64), nullable=False)
    product_name_snapshot: Mapped[str] = mapped_column(String(255), nullable=False)
    sku_code_snapshot: Mapped[str] = mapped_column(String(64), nullable=False)
    sku_name_snapshot: Mapped[str] = mapped_column(String(255), nullable=False)
    unit_price_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    line_total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    order: Mapped[ShopMindOrder] = relationship(back_populates="items")


class ShopMindInventoryReservation(Base):
    __tablename__ = "shopmind_inventory_reservations"
    __table_args__ = (
        CheckConstraint("quantity >= 1 AND quantity <= 20", name="ck_shopmind_inventory_reservations_quantity_bounds"),
        CheckConstraint("status IN ('active', 'released', 'consumed')", name="ck_shopmind_inventory_reservations_status"),
        CheckConstraint(
            "(status = 'active' AND released_at IS NULL AND consumed_at IS NULL) OR "
            "(status = 'released' AND released_at IS NOT NULL AND consumed_at IS NULL) OR "
            "(status = 'consumed' AND released_at IS NULL AND consumed_at IS NOT NULL)",
            name="ck_shopmind_inventory_reservations_release_state",
        ),
        UniqueConstraint("order_item_id", name="uq_shopmind_inventory_reservations_order_item"),
        Index("idx_shopmind_inventory_reservations_sku_status", "sku_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    order_item_id: Mapped[UUID] = mapped_column(
        ForeignKey("shopmind_order_items.id", ondelete="RESTRICT"), nullable=False
    )
    sku_id: Mapped[UUID] = mapped_column(
        ForeignKey("shopmind_product_skus.id", ondelete="RESTRICT"), nullable=False
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    released_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
