"""ShopMind PaymentAttempt persistence model."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, UniqueConstraint, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.orders import models as _order_models  # noqa: F401
from app.db.base import Base


PAYMENT_ACTIVE_STATUSES = ("processing", "unknown", "provider_succeeded")


class ShopMindPaymentAttempt(Base):
    __tablename__ = "shopmind_payment_attempts"
    __table_args__ = (
        CheckConstraint(
            "provider IN ('mock')",
            name="ck_shopmind_payment_attempts_provider",
        ),
        CheckConstraint(
            "status IN ('processing', 'unknown', 'provider_succeeded', 'failed', 'succeeded')",
            name="ck_shopmind_payment_attempts_status",
        ),
        CheckConstraint(
            "amount > 0",
            name="ck_shopmind_payment_attempts_amount_positive",
        ),
        CheckConstraint(
            "length(currency) = 3 AND currency = upper(currency)",
            name="ck_shopmind_payment_attempts_currency",
        ),
        CheckConstraint(
            "length(idempotency_key) BETWEEN 1 AND 128",
            name="ck_shopmind_payment_attempts_idempotency_key_length",
        ),
        CheckConstraint(
            "length(provider_idempotency_key) BETWEEN 1 AND 128",
            name="ck_shopmind_payment_attempts_provider_key_length",
        ),
        CheckConstraint(
            "length(request_hash) = 64",
            name="ck_shopmind_payment_attempts_request_hash_length",
        ),
        CheckConstraint(
            "(status = 'processing' AND provider_result_at IS NULL AND completed_at IS NULL AND failure_code IS NULL) OR "
            "(status = 'unknown' AND provider_result_at IS NOT NULL AND completed_at IS NULL AND failure_code IS NOT NULL) OR "
            "(status = 'provider_succeeded' AND provider_result_at IS NOT NULL AND completed_at IS NULL AND failure_code IS NULL) OR "
            "(status = 'failed' AND provider_result_at IS NOT NULL AND completed_at IS NOT NULL AND failure_code IS NOT NULL) OR "
            "(status = 'succeeded' AND provider_result_at IS NOT NULL AND completed_at IS NOT NULL AND failure_code IS NULL)",
            name="ck_shopmind_payment_attempts_outcome_consistency",
        ),
        UniqueConstraint(
            "user_id",
            "order_id",
            "idempotency_key",
            name="uq_shopmind_payment_attempts_user_order_key",
        ),
        UniqueConstraint(
            "provider",
            "provider_idempotency_key",
            name="uq_shopmind_payment_attempts_provider_key",
        ),
        Index(
            "idx_shopmind_payment_attempts_order_created_at",
            "order_id",
            "created_at",
        ),
        Index(
            "idx_shopmind_payment_attempts_user_created_at",
            "user_id",
            "created_at",
        ),
        Index(
            "uq_shopmind_payment_attempts_order_active",
            "order_id",
            unique=True,
            postgresql_where=text("status IN ('processing', 'unknown', 'provider_succeeded')"),
            sqlite_where=text("status IN ('processing', 'unknown', 'provider_succeeded')"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    order_id: Mapped[UUID] = mapped_column(
        ForeignKey("shopmind_orders.id", ondelete="RESTRICT"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="mock")
    provider_payment_id: Mapped[Optional[str]] = mapped_column(String(128))
    provider_idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="processing")
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    failure_code: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    provider_result_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
