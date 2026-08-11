"""SQLAlchemy model for ShopMind's transactional Outbox."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    BigInteger,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


JSONB_TYPE = JSON().with_variant(JSONB, "postgresql")
OUTBOX_STATUSES = ("pending", "publishing", "published", "dead_letter")


class ShopMindOutboxEvent(Base):
    """Immutable business event plus mutable delivery state."""

    __tablename__ = "shopmind_outbox_events"
    __table_args__ = (
        CheckConstraint(
            "aggregate_sequence >= 1",
            name="ck_shopmind_outbox_aggregate_sequence_positive",
        ),
        CheckConstraint(
            "event_version >= 1",
            name="ck_shopmind_outbox_event_version_positive",
        ),
        CheckConstraint(
            "status IN ('pending', 'publishing', 'published', 'dead_letter')",
            name="ck_shopmind_outbox_status",
        ),
        CheckConstraint(
            "attempt_count >= 0",
            name="ck_shopmind_outbox_attempt_count_nonnegative",
        ),
        CheckConstraint(
            "redrive_count >= 0",
            name="ck_shopmind_outbox_redrive_count_nonnegative",
        ),
        CheckConstraint(
            "(status = 'publishing' AND lease_owner IS NOT NULL AND lease_until IS NOT NULL) OR "
            "(status IN ('pending', 'published', 'dead_letter') AND lease_owner IS NULL AND lease_until IS NULL)",
            name="ck_shopmind_outbox_lease_state",
        ),
        CheckConstraint(
            "(status = 'published' AND published_at IS NOT NULL) OR "
            "(status <> 'published' AND published_at IS NULL)",
            name="ck_shopmind_outbox_published_state",
        ),
        UniqueConstraint(
            "aggregate_type",
            "aggregate_id",
            "aggregate_sequence",
            name="uq_shopmind_outbox_aggregate_sequence",
        ),
        Index(
            "idx_shopmind_outbox_claim",
            "status",
            "available_at",
            "lease_until",
            "created_at",
            "id",
        ),
        Index(
            "idx_shopmind_outbox_aggregate_order",
            "aggregate_type",
            "aggregate_id",
            "aggregate_sequence",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    aggregate_sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    event_version: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB_TYPE, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    redrive_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    lease_owner: Mapped[Optional[UUID]] = mapped_column(Uuid(as_uuid=True))
    lease_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[Optional[str]] = mapped_column(String(1024))
    broker_message_id: Mapped[Optional[str]] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
