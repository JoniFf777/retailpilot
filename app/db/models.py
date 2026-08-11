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
    UniqueConstraint,
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
            "status IN ('pending', 'confirmed', 'cancelled', 'expired', 'failed')",
            name="ck_pending_actions_status",
        ),
        CheckConstraint("version >= 1", name="ck_pending_actions_version_positive"),
        Index("idx_pending_actions_user_status", "user_id", "status"),
        Index("idx_pending_actions_thread", "thread_id"),
        Index("idx_pending_actions_expires_at", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, nullable=False)
    thread_id: Mapped[Optional[str]] = mapped_column(String)
    action_type: Mapped[str] = mapped_column(String, nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSONB_TYPE, nullable=False)
    risk_class: Mapped[str] = mapped_column(String, nullable=False, default="high")
    preview_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String, nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    metadata_json: Mapped[dict] = mapped_column(
        JSONB_TYPE, nullable=False, server_default="{}"
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    result_json: Mapped[dict] = mapped_column(
        JSONB_TYPE, nullable=False, server_default="{}"
    )
    resolution_request_hash: Mapped[Optional[str]] = mapped_column(String(128))
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
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


class ConversationThread(Base):
    __tablename__ = "conversation_threads"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'archived', 'deleted')",
            name="ck_conversation_threads_status",
        ),
        UniqueConstraint(
            "user_id",
            "client_thread_id",
            name="uq_conversation_threads_user_client_thread",
        ),
        Index("idx_conversation_threads_user_updated_at", "user_id", "updated_at"),
        Index("idx_conversation_threads_status", "status"),
        Index("idx_conversation_threads_expires_at", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[Optional[str]] = mapped_column(String)
    client_thread_id: Mapped[Optional[str]] = mapped_column(String)
    title: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    metadata_json: Mapped[dict] = mapped_column(
        JSONB_TYPE, nullable=False, server_default="{}"
    )
    last_message_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    messages: Mapped[list["ConversationMessage"]] = relationship(
        back_populates="thread", cascade="all, delete-orphan"
    )
    runs: Mapped[list["AgentRun"]] = relationship(
        back_populates="thread", cascade="all, delete-orphan"
    )
    summaries: Mapped[list["ConversationSummary"]] = relationship(
        back_populates="thread", cascade="all, delete-orphan"
    )
    memory_records: Mapped[list["MemoryRecord"]] = relationship(
        back_populates="thread", cascade="all, delete-orphan"
    )


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"
    __table_args__ = (
        CheckConstraint(
            "role IN ('user', 'assistant', 'system', 'tool')",
            name="ck_conversation_messages_role",
        ),
        CheckConstraint(
            "message_type IN ('message', 'event', 'summary', 'action', 'debug')",
            name="ck_conversation_messages_type",
        ),
        UniqueConstraint(
            "thread_id",
            "sequence",
            name="uq_conversation_messages_thread_sequence",
        ),
        Index("idx_conversation_messages_user_created_at", "user_id", "created_at"),
        Index("idx_conversation_messages_thread_created_at", "thread_id", "created_at"),
        Index("idx_conversation_messages_run_id", "run_id"),
        Index("idx_conversation_messages_expires_at", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    thread_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("conversation_threads.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[Optional[str]] = mapped_column(String)
    run_id: Mapped[Optional[str]] = mapped_column(String)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    message_type: Mapped[str] = mapped_column(String, nullable=False, default="message")
    content_text: Mapped[Optional[str]] = mapped_column(Text)
    content_json: Mapped[dict] = mapped_column(
        JSONB_TYPE, nullable=False, server_default="{}"
    )
    metadata_json: Mapped[dict] = mapped_column(
        JSONB_TYPE, nullable=False, server_default="{}"
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    thread: Mapped["ConversationThread"] = relationship(back_populates="messages")


class AgentRun(Base):
    __tablename__ = "agent_runs"
    __table_args__ = (
        CheckConstraint(
            "operation IN ('chat', 'confirm_pending_action')",
            name="ck_agent_runs_operation",
        ),
        CheckConstraint(
            "mode IN ('single', 'multi')",
            name="ck_agent_runs_mode",
        ),
        CheckConstraint(
            "status IN ('started', 'completed', 'confirmation_required', 'cancelled', 'failed')",
            name="ck_agent_runs_status",
        ),
        UniqueConstraint(
            "user_id",
            "operation",
            "idempotency_key",
            name="uq_agent_runs_user_operation_idempotency_key",
        ),
        Index("idx_agent_runs_thread_started_at", "thread_id", "started_at"),
        Index("idx_agent_runs_user_started_at", "user_id", "started_at"),
        Index("idx_agent_runs_trace_id", "trace_id"),
        Index("idx_agent_runs_expires_at", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    thread_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("conversation_threads.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[Optional[str]] = mapped_column(String)
    parent_run_id: Mapped[Optional[str]] = mapped_column(
        String,
        ForeignKey("agent_runs.id", ondelete="SET NULL"),
    )
    operation: Mapped[str] = mapped_column(String, nullable=False)
    mode: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    request_id: Mapped[str] = mapped_column(String, nullable=False)
    trace_id: Mapped[str] = mapped_column(String, nullable=False)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String)
    pending_action_id: Mapped[Optional[str]] = mapped_column(String)
    input_text: Mapped[Optional[str]] = mapped_column(Text)
    output_text: Mapped[Optional[str]] = mapped_column(Text)
    request_json: Mapped[dict] = mapped_column(
        JSONB_TYPE, nullable=False, server_default="{}"
    )
    result_json: Mapped[dict] = mapped_column(
        JSONB_TYPE, nullable=False, server_default="{}"
    )
    error_json: Mapped[Optional[dict]] = mapped_column(JSONB_TYPE)
    usage_json: Mapped[dict] = mapped_column(
        JSONB_TYPE, nullable=False, server_default="{}"
    )
    debug_json: Mapped[Optional[dict]] = mapped_column(JSONB_TYPE)
    tool_call_records_json: Mapped[list] = mapped_column(
        JSONB_TYPE, nullable=False, server_default="[]"
    )
    metadata_json: Mapped[dict] = mapped_column(
        JSONB_TYPE, nullable=False, server_default="{}"
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    thread: Mapped["ConversationThread"] = relationship(back_populates="runs")
    events: Mapped[list["AgentRunEvent"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class AgentRunEvent(Base):
    __tablename__ = "agent_run_events"
    __table_args__ = (
        CheckConstraint(
            "visibility IN ('client', 'internal', 'audit')",
            name="ck_agent_run_events_visibility",
        ),
        UniqueConstraint(
            "run_id",
            "sequence",
            name="uq_agent_run_events_run_sequence",
        ),
        Index("idx_agent_run_events_thread_created_at", "thread_id", "created_at"),
        Index("idx_agent_run_events_user_created_at", "user_id", "created_at"),
        Index("idx_agent_run_events_trace_id", "trace_id"),
    )

    id: Mapped[int] = mapped_column(BIGINT_ID, Identity(), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    thread_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("conversation_threads.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[Optional[str]] = mapped_column(String)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    agent_name: Mapped[Optional[str]] = mapped_column(String)
    visibility: Mapped[str] = mapped_column(String, nullable=False)
    payload_json: Mapped[dict] = mapped_column(
        JSONB_TYPE, nullable=False, server_default="{}"
    )
    trace_id: Mapped[Optional[str]] = mapped_column(String)
    tool_call_id: Mapped[Optional[str]] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    run: Mapped["AgentRun"] = relationship(back_populates="events")


class ConversationSummary(Base):
    __tablename__ = "conversation_summaries"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'superseded', 'deleted')",
            name="ck_conversation_summaries_status",
        ),
        CheckConstraint(
            "start_message_sequence > 0",
            name="ck_conversation_summaries_start_positive",
        ),
        CheckConstraint(
            "end_message_sequence >= start_message_sequence",
            name="ck_conversation_summaries_range",
        ),
        UniqueConstraint(
            "thread_id",
            "start_message_sequence",
            "end_message_sequence",
            name="uq_conversation_summaries_thread_range",
        ),
        Index("idx_conversation_summaries_user_created_at", "user_id", "created_at"),
        Index("idx_conversation_summaries_thread_created_at", "thread_id", "created_at"),
        Index("idx_conversation_summaries_expires_at", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    thread_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("conversation_threads.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[Optional[str]] = mapped_column(String)
    source_run_id: Mapped[Optional[str]] = mapped_column(
        String,
        ForeignKey("agent_runs.id", ondelete="SET NULL"),
    )
    start_message_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    end_message_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)
    summary_json: Mapped[dict] = mapped_column(
        JSONB_TYPE, nullable=False, server_default="{}"
    )
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    thread: Mapped["ConversationThread"] = relationship(back_populates="summaries")


class MemoryRecord(Base):
    __tablename__ = "runtime_memory_records"
    __table_args__ = (
        CheckConstraint(
            "memory_kind IN ('working', 'episodic', 'long_term', 'operational')",
            name="ck_runtime_memory_kind",
        ),
        CheckConstraint(
            "scope IN ('thread', 'user', 'operational')",
            name="ck_runtime_memory_scope",
        ),
        CheckConstraint(
            "status IN ('active', 'superseded', 'deleted')",
            name="ck_runtime_memory_status",
        ),
        CheckConstraint("priority >= 0", name="ck_runtime_memory_priority"),
        CheckConstraint("token_count >= 0", name="ck_runtime_memory_token_count"),
        Index("idx_runtime_memory_user_kind_created_at", "user_id", "memory_kind", "created_at"),
        Index("idx_runtime_memory_thread_created_at", "thread_id", "created_at"),
        Index("idx_runtime_memory_expires_at", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[Optional[str]] = mapped_column(String)
    thread_id: Mapped[Optional[str]] = mapped_column(
        String,
        ForeignKey("conversation_threads.id", ondelete="CASCADE"),
    )
    source_run_id: Mapped[Optional[str]] = mapped_column(
        String,
        ForeignKey("agent_runs.id", ondelete="SET NULL"),
    )
    source_message_id: Mapped[Optional[str]] = mapped_column(
        String,
        ForeignKey("conversation_messages.id", ondelete="SET NULL"),
    )
    memory_kind: Mapped[str] = mapped_column(String, nullable=False)
    scope: Mapped[str] = mapped_column(String, nullable=False)
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    content_json: Mapped[dict] = mapped_column(
        JSONB_TYPE, nullable=False, server_default="{}"
    )
    provenance_json: Mapped[dict] = mapped_column(
        JSONB_TYPE, nullable=False, server_default="{}"
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    confidence: Mapped[Optional[float]] = mapped_column(Numeric(5, 4))
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    thread: Mapped[Optional["ConversationThread"]] = relationship(
        back_populates="memory_records"
    )


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        CheckConstraint(
            "status IN ('started', 'completed', 'confirmation_required', 'cancelled', 'failed')",
            name="ck_idempotency_records_status",
        ),
        UniqueConstraint(
            "user_id",
            "operation",
            "idempotency_key",
            name="uq_idempotency_records_user_operation_key",
        ),
        Index("idx_idempotency_records_thread_created_at", "thread_id", "created_at"),
        Index("idx_idempotency_records_expires_at", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[Optional[str]] = mapped_column(String)
    thread_id: Mapped[Optional[str]] = mapped_column(
        String,
        ForeignKey("conversation_threads.id", ondelete="CASCADE"),
    )
    run_id: Mapped[Optional[str]] = mapped_column(
        String,
        ForeignKey("agent_runs.id", ondelete="SET NULL"),
    )
    operation: Mapped[str] = mapped_column(String, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String, nullable=False)
    request_hash: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    response_fingerprint: Mapped[Optional[str]] = mapped_column(String)
    metadata_json: Mapped[dict] = mapped_column(
        JSONB_TYPE, nullable=False, server_default="{}"
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class GovernanceAuditRecord(Base):
    __tablename__ = "governance_audit_records"
    __table_args__ = (
        CheckConstraint(
            "schema_version = 'shopmind.governance-audit.v1'",
            name="ck_governance_audit_schema_version",
        ),
        CheckConstraint(
            "category IN ('authentication', 'tool', 'action', 'memory', 'deletion')",
            name="ck_governance_audit_category",
        ),
        CheckConstraint(
            "operation IN ("
            "'authentication.bind', 'tool.invoke', "
            "'action.prepare', 'action.resume', 'action.confirm', "
            "'action.cancel', 'action.expire', "
            "'memory.create', 'memory.inspect', 'memory.correct', 'memory.delete', "
            "'deletion.request', 'deletion.execute'"
            ")",
            name="ck_governance_audit_operation",
        ),
        CheckConstraint(
            "decision IN ("
            "'allowed', 'denied', 'requested', 'succeeded', "
            "'failed', 'skipped', 'not_found'"
            ")",
            name="ck_governance_audit_decision",
        ),
        CheckConstraint(
            "reason IN ("
            "'authenticated', 'anonymous_compatibility', "
            "'authentication_required', 'owner_matched', 'owner_mismatch', "
            "'policy_allowed', 'policy_denied', 'completed', "
            "'validation_failed', 'provider_failed', 'not_found', 'expired', "
            "'user_requested', 'retention_expired', 'already_deleted', "
            "'cancelled', 'budget_blocked'"
            ")",
            name="ck_governance_audit_reason",
        ),
        CheckConstraint(
            "actor_kind IN ('principal', 'system', 'anonymous')",
            name="ck_governance_audit_actor_kind",
        ),
        CheckConstraint(
            "actor_fingerprint IS NULL OR length(actor_fingerprint) = 64",
            name="ck_governance_audit_actor_fingerprint",
        ),
        CheckConstraint(
            "owner_fingerprint IS NULL OR length(owner_fingerprint) = 64",
            name="ck_governance_audit_owner_fingerprint",
        ),
        CheckConstraint(
            "thread_fingerprint IS NULL OR length(thread_fingerprint) = 64",
            name="ck_governance_audit_thread_fingerprint",
        ),
        CheckConstraint(
            "run_fingerprint IS NULL OR length(run_fingerprint) = 64",
            name="ck_governance_audit_run_fingerprint",
        ),
        CheckConstraint(
            "resource_fingerprint IS NULL OR length(resource_fingerprint) = 64",
            name="ck_governance_audit_resource_fingerprint",
        ),
        CheckConstraint(
            "expires_at > occurred_at",
            name="ck_governance_audit_retention_window",
        ),
        Index(
            "idx_governance_audit_owner_occurred_at",
            "owner_fingerprint",
            "occurred_at",
        ),
        Index(
            "idx_governance_audit_category_occurred_at",
            "category",
            "occurred_at",
        ),
        Index(
            "idx_governance_audit_run_occurred_at",
            "run_fingerprint",
            "occurred_at",
        ),
        Index(
            "idx_governance_audit_resource",
            "resource_fingerprint",
        ),
        Index("idx_governance_audit_expires_at", "expires_at"),
    )

    audit_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    operation: Mapped[str] = mapped_column(String(64), nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_fingerprint: Mapped[Optional[str]] = mapped_column(String(64))
    owner_fingerprint: Mapped[Optional[str]] = mapped_column(String(64))
    thread_fingerprint: Mapped[Optional[str]] = mapped_column(String(64))
    run_fingerprint: Mapped[Optional[str]] = mapped_column(String(64))
    resource_fingerprint: Mapped[Optional[str]] = mapped_column(String(64))
    metadata_json: Mapped[dict] = mapped_column(
        JSONB_TYPE, nullable=False, server_default="{}"
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
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
