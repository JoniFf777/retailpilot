"""add scoped runtime memory records

Revision ID: 0005_runtime_memory_records
Revises: 0004_runtime_persistence
Create Date: 2026-07-14 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0005_runtime_memory_records"
down_revision: Union[str, None] = "0004_runtime_persistence"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "runtime_memory_records",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("thread_id", sa.String(), nullable=True),
        sa.Column("source_run_id", sa.String(), nullable=True),
        sa.Column("source_message_id", sa.String(), nullable=True),
        sa.Column("memory_kind", sa.String(), nullable=False),
        sa.Column("scope", sa.String(), nullable=False),
        sa.Column("content_text", sa.Text(), nullable=False),
        sa.Column(
            "content_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "provenance_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("token_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "memory_kind IN ('working', 'episodic', 'long_term', 'operational')",
            name="ck_runtime_memory_kind",
        ),
        sa.CheckConstraint(
            "scope IN ('thread', 'user', 'operational')",
            name="ck_runtime_memory_scope",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'superseded', 'deleted')",
            name="ck_runtime_memory_status",
        ),
        sa.CheckConstraint("priority >= 0", name="ck_runtime_memory_priority"),
        sa.CheckConstraint("token_count >= 0", name="ck_runtime_memory_token_count"),
        sa.ForeignKeyConstraint(
            ["thread_id"], ["conversation_threads.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["source_run_id"], ["agent_runs.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["source_message_id"], ["conversation_messages.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_runtime_memory_user_kind_created_at",
        "runtime_memory_records",
        ["user_id", "memory_kind", "created_at"],
    )
    op.create_index(
        "idx_runtime_memory_thread_created_at",
        "runtime_memory_records",
        ["thread_id", "created_at"],
    )
    op.create_index(
        "idx_runtime_memory_expires_at",
        "runtime_memory_records",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_runtime_memory_expires_at", table_name="runtime_memory_records")
    op.drop_index(
        "idx_runtime_memory_thread_created_at", table_name="runtime_memory_records"
    )
    op.drop_index(
        "idx_runtime_memory_user_kind_created_at", table_name="runtime_memory_records"
    )
    op.drop_table("runtime_memory_records")
