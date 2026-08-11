"""add the ShopMind transactional Outbox event store

Revision ID: 0014_shopmind_outbox_events
Revises: 0013_shopmind_payments
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0014_shopmind_outbox_events"
down_revision: Union[str, None] = "0013_shopmind_payments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "shopmind_outbox_events",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("aggregate_type", sa.String(length=64), nullable=False),
        sa.Column("aggregate_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("aggregate_sequence", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("event_version", sa.Integer(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("redrive_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("lease_owner", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=1024), nullable=True),
        sa.Column("broker_message_id", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "aggregate_sequence >= 1",
            name="ck_shopmind_outbox_aggregate_sequence_positive",
        ),
        sa.CheckConstraint(
            "event_version >= 1",
            name="ck_shopmind_outbox_event_version_positive",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'publishing', 'published', 'dead_letter')",
            name="ck_shopmind_outbox_status",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="ck_shopmind_outbox_attempt_count_nonnegative",
        ),
        sa.CheckConstraint(
            "redrive_count >= 0",
            name="ck_shopmind_outbox_redrive_count_nonnegative",
        ),
        sa.CheckConstraint(
            "(status = 'publishing' AND lease_owner IS NOT NULL AND lease_until IS NOT NULL) OR "
            "(status IN ('pending', 'published', 'dead_letter') AND lease_owner IS NULL AND lease_until IS NULL)",
            name="ck_shopmind_outbox_lease_state",
        ),
        sa.CheckConstraint(
            "(status = 'published' AND published_at IS NOT NULL) OR "
            "(status <> 'published' AND published_at IS NULL)",
            name="ck_shopmind_outbox_published_state",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "aggregate_type",
            "aggregate_id",
            "aggregate_sequence",
            name="uq_shopmind_outbox_aggregate_sequence",
        ),
    )
    op.create_index(
        "idx_shopmind_outbox_claim",
        "shopmind_outbox_events",
        ["status", "available_at", "lease_until", "created_at", "id"],
    )
    op.create_index(
        "idx_shopmind_outbox_aggregate_order",
        "shopmind_outbox_events",
        ["aggregate_type", "aggregate_id", "aggregate_sequence"],
    )


def downgrade() -> None:
    op.drop_index("idx_shopmind_outbox_aggregate_order", table_name="shopmind_outbox_events")
    op.drop_index("idx_shopmind_outbox_claim", table_name="shopmind_outbox_events")
    op.drop_table("shopmind_outbox_events")
