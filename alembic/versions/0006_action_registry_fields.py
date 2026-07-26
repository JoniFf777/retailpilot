"""add structured action registry fields

Revision ID: 0006_action_registry_fields
Revises: 0005_runtime_memory_records
Create Date: 2026-07-14 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0006_action_registry_fields"
down_revision: Union[str, None] = "0005_runtime_memory_records"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "pending_actions",
        sa.Column(
            "risk_class",
            sa.String(),
            server_default=sa.text("'high'"),
            nullable=False,
        ),
    )
    op.add_column(
        "pending_actions",
        sa.Column(
            "preview_text",
            sa.Text(),
            server_default=sa.text("''"),
            nullable=False,
        ),
    )
    op.add_column(
        "pending_actions",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "pending_actions",
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.drop_constraint(
        "ck_pending_actions_status",
        "pending_actions",
        type_="check",
    )
    op.create_check_constraint(
        "ck_pending_actions_status",
        "pending_actions",
        "status IN ('pending', 'confirmed', 'cancelled', 'expired', 'failed')",
    )
    op.create_index(
        "idx_pending_actions_expires_at",
        "pending_actions",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_pending_actions_expires_at", table_name="pending_actions")
    op.drop_constraint(
        "ck_pending_actions_status",
        "pending_actions",
        type_="check",
    )
    op.create_check_constraint(
        "ck_pending_actions_status",
        "pending_actions",
        "status IN ('pending', 'confirmed', 'cancelled')",
    )
    op.drop_column("pending_actions", "metadata_json")
    op.drop_column("pending_actions", "expires_at")
    op.drop_column("pending_actions", "preview_text")
    op.drop_column("pending_actions", "risk_class")
