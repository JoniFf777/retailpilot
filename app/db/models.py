"""SQLAlchemy ORM models for ShopMind V2 data."""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import UserDefinedType

from app.db.base import Base


BIGINT_ID = BigInteger().with_variant(Integer, "sqlite")
JSONB_TYPE = JSON().with_variant(JSONB, "postgresql")
DEFAULT_DOCUMENT_VECTOR_DIMENSION = 768


class VectorType(UserDefinedType):
    """Minimal pgvector type with SQLite-friendly test compilation."""

    cache_ok = True

    def __init__(self, dimension: int):
        self.dimension = dimension

    def get_col_spec(self, **kw):
        return f"vector({self.dimension})"


@compiles(VectorType, "sqlite")
def _compile_vector_sqlite(type_, compiler, **kw):
    return "TEXT"


@compiles(VectorType, "postgresql")
def _compile_vector_postgresql(type_, compiler, **kw):
    return f"vector({type_.dimension})"


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (
        CheckConstraint(
            "segment IN ('Consumer', 'Corporate', 'Home Office')",
            name="ck_customers_segment",
        ),
        Index("idx_customers_email", "email"),
    )

    customer_id: Mapped[str] = mapped_column(String, primary_key=True)
    email: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String)
    city: Mapped[str] = mapped_column(String, nullable=False)
    state: Mapped[str] = mapped_column(String, nullable=False)
    segment: Mapped[str] = mapped_column(String, nullable=False)

    orders: Mapped[list["Order"]] = relationship(back_populates="customer")


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint(
            "category IN ('Laptops', 'Monitors', 'Keyboards', 'Audio', 'Accessories')",
            name="ck_products_category",
        ),
        CheckConstraint("price > 0", name="ck_products_price_positive"),
        Index("idx_products_category", "category"),
        Index("idx_products_in_stock", "in_stock"),
    )

    product_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    in_stock: Mapped[bool] = mapped_column(Boolean, nullable=False)

    order_items: Mapped[list["OrderItem"]] = relationship(back_populates="product")
    cart_items: Mapped[list["CartItem"]] = relationship(back_populates="product")


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint(
            "status IN ('Processing', 'Shipped', 'Delivered', 'Cancelled')",
            name="ck_orders_status",
        ),
        CheckConstraint("total_amount >= 0", name="ck_orders_total_amount_nonnegative"),
        Index("idx_orders_customer", "customer_id"),
        Index("idx_orders_date", "order_date"),
        Index("idx_orders_status", "status"),
    )

    order_id: Mapped[str] = mapped_column(String, primary_key=True)
    customer_id: Mapped[str] = mapped_column(
        String, ForeignKey("customers.customer_id"), nullable=False
    )
    order_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    shipped_date: Mapped[Optional[date]] = mapped_column(Date)
    tracking_number: Mapped[Optional[str]] = mapped_column(String)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    customer: Mapped["Customer"] = relationship(back_populates="orders")
    order_items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_order_items_quantity_positive"),
        CheckConstraint("price_per_unit > 0", name="ck_order_items_price_positive"),
        Index("idx_order_items_order", "order_id"),
        Index("idx_order_items_product", "product_id"),
    )

    order_item_id: Mapped[int] = mapped_column(BIGINT_ID, Identity(), primary_key=True)
    order_id: Mapped[str] = mapped_column(
        String, ForeignKey("orders.order_id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[str] = mapped_column(
        String, ForeignKey("products.product_id"), nullable=False
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    price_per_unit: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    order: Mapped["Order"] = relationship(back_populates="order_items")
    product: Mapped["Product"] = relationship(back_populates="order_items")


class UserPreference(Base):
    __tablename__ = "user_preferences"
    __table_args__ = (
        CheckConstraint(
            "preference_type IN ('budget', 'brand', 'avoid', 'usage', 'style', 'other')",
            name="ck_user_preferences_type",
        ),
        Index("idx_user_preferences_user", "user_id"),
    )

    id: Mapped[int] = mapped_column(BIGINT_ID, Identity(), primary_key=True)
    user_id: Mapped[str] = mapped_column(String, nullable=False)
    preference_type: Mapped[str] = mapped_column(String, nullable=False)
    preference_value: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CartItem(Base):
    __tablename__ = "cart_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_cart_items_quantity_positive"),
        Index("idx_cart_items_user", "user_id"),
        Index("idx_cart_items_product", "product_id"),
    )

    id: Mapped[int] = mapped_column(BIGINT_ID, Identity(), primary_key=True)
    user_id: Mapped[str] = mapped_column(String, nullable=False)
    product_id: Mapped[str] = mapped_column(
        String, ForeignKey("products.product_id"), nullable=False
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    product: Mapped["Product"] = relationship(back_populates="cart_items")


class PendingAction(Base):
    __tablename__ = "pending_actions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'confirmed', 'cancelled')",
            name="ck_pending_actions_status",
        ),
        Index("idx_pending_actions_user_status", "user_id", "status"),
        Index("idx_pending_actions_thread", "thread_id"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, nullable=False)
    thread_id: Mapped[Optional[str]] = mapped_column(String)
    action_type: Mapped[str] = mapped_column(String, nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSONB_TYPE, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CandidateContext(Base):
    __tablename__ = "candidate_contexts"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_candidate_contexts_quantity_positive"),
        Index("idx_candidate_contexts_expires_at", "expires_at"),
    )

    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    thread_id: Mapped[str] = mapped_column(String, primary_key=True)
    product_ids: Mapped[list[str]] = mapped_column(JSONB_TYPE, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            "doc_type IN ('product', 'policy')",
            name="ck_documents_doc_type",
        ),
        Index("idx_documents_doc_type", "doc_type"),
        Index("idx_documents_product_id", "product_id"),
        Index("idx_documents_source_path", "source_path"),
        Index("idx_documents_metadata_json", "metadata_json", postgresql_using="gin"),
        Index(
            "idx_documents_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(BIGINT_ID, Identity(), primary_key=True)
    doc_type: Mapped[str] = mapped_column(String, nullable=False)
    source_path: Mapped[str] = mapped_column(Text, nullable=False)
    source_name: Mapped[Optional[str]] = mapped_column(Text)
    product_id: Mapped[Optional[str]] = mapped_column(String)
    product_name: Mapped[Optional[str]] = mapped_column(Text)
    policy_name: Mapped[Optional[str]] = mapped_column(Text)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(
        JSONB_TYPE, nullable=False, server_default="{}"
    )
    embedding: Mapped[str] = mapped_column(
        VectorType(DEFAULT_DOCUMENT_VECTOR_DIMENSION), nullable=False
    )
    embedding_provider: Mapped[str] = mapped_column(String, nullable=False)
    embedding_model: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
