"""ORM model for the new SKU-based ShopMind cart.

The legacy ``cart_items`` table remains owned by the V2 compatibility path.
This table deliberately starts empty and has no relationship to legacy Product.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from .constants import MAX_CART_ITEM_QUANTITY
# Import Catalog models when the cart model is imported so standalone SQLite
# metadata tests can resolve the SKU foreign key without Alembic side effects.
from app.catalog import models as _catalog_models  # noqa: F401

if TYPE_CHECKING:
    from app.catalog.models import CatalogSku


class ShopMindCartItem(Base):
    __tablename__ = "shopmind_cart_items"
    __table_args__ = (
        CheckConstraint("quantity >= 1", name="ck_shopmind_cart_items_quantity_positive"),
        CheckConstraint(
            f"quantity <= {MAX_CART_ITEM_QUANTITY}",
            name="ck_shopmind_cart_items_quantity_max",
        ),
        CheckConstraint("version >= 1", name="ck_shopmind_cart_items_version_positive"),
        UniqueConstraint("user_id", "sku_id", name="uq_shopmind_cart_items_user_sku"),
        Index("idx_shopmind_cart_items_user_updated_at", "user_id", "updated_at"),
        Index("idx_shopmind_cart_items_sku", "sku_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[str] = mapped_column(String, nullable=False)
    sku_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("shopmind_product_skus.id", ondelete="RESTRICT"),
        nullable=False,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
