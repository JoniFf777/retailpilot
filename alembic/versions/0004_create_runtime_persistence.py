"""create runtime persistence tables

Revision ID: 0004_runtime_persistence
Revises: 0003_candidate_contexts
Create Date: 2026-07-13 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0004_runtime_persistence"
down_revision: Union[str, None] = "0003_candidate_contexts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "conversation_threads",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("client_thread_id", sa.String(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
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
            "status IN ('active', 'archived', 'deleted')",
            name="ck_conversation_threads_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "client_thread_id",
            name="uq_conversation_threads_user_client_thread",
        ),
    )
    op.create_index(
        "idx_conversation_threads_user_updated_at",
        "conversation_threads",
        ["user_id", "updated_at"],
    )
    op.create_index(
        "idx_conversation_threads_status",
        "conversation_threads",
        ["status"],
    )
    op.create_index(
        "idx_conversation_threads_expires_at",
        "conversation_threads",
        ["expires_at"],
    )

    op.create_table(
        "agent_runs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("thread_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("parent_run_id", sa.String(), nullable=True),
        sa.Column("operation", sa.String(), nullable=False),
        sa.Column("mode", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("request_id", sa.String(), nullable=False),
        sa.Column("trace_id", sa.String(), nullable=False),
        sa.Column("idempotency_key", sa.String(), nullable=True),
        sa.Column("pending_action_id", sa.String(), nullable=True),
        sa.Column("input_text", sa.Text(), nullable=True),
        sa.Column("output_text", sa.Text(), nullable=True),
        sa.Column(
            "request_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "result_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("error_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "usage_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("debug_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "tool_call_records_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
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
            "operation IN ('chat', 'confirm_pending_action')",
            name="ck_agent_runs_operation",
        ),
        sa.CheckConstraint(
            "mode IN ('single', 'multi')",
            name="ck_agent_runs_mode",
        ),
        sa.CheckConstraint(
            "status IN ('started', 'completed', 'confirmation_required', 'cancelled', 'failed')",
            name="ck_agent_runs_status",
        ),
        sa.ForeignKeyConstraint(
            ["parent_run_id"],
            ["agent_runs.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["thread_id"],
            ["conversation_threads.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "operation",
            "idempotency_key",
            name="uq_agent_runs_user_operation_idempotency_key",
        ),
    )
    op.create_index(
        "idx_agent_runs_thread_started_at",
        "agent_runs",
        ["thread_id", "started_at"],
    )
    op.create_index(
        "idx_agent_runs_user_started_at",
        "agent_runs",
        ["user_id", "started_at"],
    )
    op.create_index(
        "idx_agent_runs_trace_id",
        "agent_runs",
        ["trace_id"],
    )
    op.create_index(
        "idx_agent_runs_expires_at",
        "agent_runs",
        ["expires_at"],
    )

    op.create_table(
        "conversation_messages",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("thread_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("run_id", sa.String(), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("message_type", sa.String(), nullable=False),
        sa.Column("content_text", sa.Text(), nullable=True),
        sa.Column(
            "content_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
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
            "role IN ('user', 'assistant', 'system', 'tool')",
            name="ck_conversation_messages_role",
        ),
        sa.CheckConstraint(
            "message_type IN ('message', 'event', 'summary', 'action', 'debug')",
            name="ck_conversation_messages_type",
        ),
        sa.ForeignKeyConstraint(
            ["thread_id"],
            ["conversation_threads.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "thread_id",
            "sequence",
            name="uq_conversation_messages_thread_sequence",
        ),
    )
    op.create_index(
        "idx_conversation_messages_user_created_at",
        "conversation_messages",
        ["user_id", "created_at"],
    )
    op.create_index(
        "idx_conversation_messages_thread_created_at",
        "conversation_messages",
        ["thread_id", "created_at"],
    )
    op.create_index(
        "idx_conversation_messages_run_id",
        "conversation_messages",
        ["run_id"],
    )
    op.create_index(
        "idx_conversation_messages_expires_at",
        "conversation_messages",
        ["expires_at"],
    )

    op.create_table(
        "agent_run_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("thread_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("agent_name", sa.String(), nullable=True),
        sa.Column("visibility", sa.String(), nullable=False),
        sa.Column(
            "payload_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("trace_id", sa.String(), nullable=True),
        sa.Column("tool_call_id", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "visibility IN ('client', 'internal', 'audit')",
            name="ck_agent_run_events_visibility",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["agent_runs.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["thread_id"],
            ["conversation_threads.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id",
            "sequence",
            name="uq_agent_run_events_run_sequence",
        ),
    )
    op.create_index(
        "idx_agent_run_events_thread_created_at",
        "agent_run_events",
        ["thread_id", "created_at"],
    )
    op.create_index(
        "idx_agent_run_events_user_created_at",
        "agent_run_events",
        ["user_id", "created_at"],
    )
    op.create_index(
        "idx_agent_run_events_trace_id",
        "agent_run_events",
        ["trace_id"],
    )

    op.create_table(
        "conversation_summaries",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("thread_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("source_run_id", sa.String(), nullable=True),
        sa.Column("start_message_sequence", sa.Integer(), nullable=False),
        sa.Column("end_message_sequence", sa.Integer(), nullable=False),
        sa.Column("summary_text", sa.Text(), nullable=False),
        sa.Column(
            "summary_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("status", sa.String(), nullable=False),
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
            "status IN ('active', 'superseded', 'deleted')",
            name="ck_conversation_summaries_status",
        ),
        sa.CheckConstraint(
            "start_message_sequence > 0",
            name="ck_conversation_summaries_start_positive",
        ),
        sa.CheckConstraint(
            "end_message_sequence >= start_message_sequence",
            name="ck_conversation_summaries_range",
        ),
        sa.ForeignKeyConstraint(
            ["source_run_id"],
            ["agent_runs.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["thread_id"],
            ["conversation_threads.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "thread_id",
            "start_message_sequence",
            "end_message_sequence",
            name="uq_conversation_summaries_thread_range",
        ),
    )
    op.create_index(
        "idx_conversation_summaries_user_created_at",
        "conversation_summaries",
        ["user_id", "created_at"],
    )
    op.create_index(
        "idx_conversation_summaries_thread_created_at",
        "conversation_summaries",
        ["thread_id", "created_at"],
    )
    op.create_index(
        "idx_conversation_summaries_expires_at",
        "conversation_summaries",
        ["expires_at"],
    )

    op.create_table(
        "idempotency_records",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("thread_id", sa.String(), nullable=True),
        sa.Column("run_id", sa.String(), nullable=True),
        sa.Column("operation", sa.String(), nullable=False),
        sa.Column("idempotency_key", sa.String(), nullable=False),
        sa.Column("request_hash", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("response_fingerprint", sa.String(), nullable=True),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
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
            "status IN ('started', 'completed', 'confirmation_required', 'cancelled', 'failed')",
            name="ck_idempotency_records_status",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["agent_runs.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["thread_id"],
            ["conversation_threads.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "operation",
            "idempotency_key",
            name="uq_idempotency_records_user_operation_key",
        ),
    )
    op.create_index(
        "idx_idempotency_records_thread_created_at",
        "idempotency_records",
        ["thread_id", "created_at"],
    )
    op.create_index(
        "idx_idempotency_records_expires_at",
        "idempotency_records",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_idempotency_records_expires_at",
        table_name="idempotency_records",
    )
    op.drop_index(
        "idx_idempotency_records_thread_created_at",
        table_name="idempotency_records",
    )
    op.drop_table("idempotency_records")

    op.drop_index(
        "idx_conversation_summaries_expires_at",
        table_name="conversation_summaries",
    )
    op.drop_index(
        "idx_conversation_summaries_thread_created_at",
        table_name="conversation_summaries",
    )
    op.drop_index(
        "idx_conversation_summaries_user_created_at",
        table_name="conversation_summaries",
    )
    op.drop_table("conversation_summaries")

    op.drop_index(
        "idx_agent_run_events_trace_id",
        table_name="agent_run_events",
    )
    op.drop_index(
        "idx_agent_run_events_user_created_at",
        table_name="agent_run_events",
    )
    op.drop_index(
        "idx_agent_run_events_thread_created_at",
        table_name="agent_run_events",
    )
    op.drop_table("agent_run_events")

    op.drop_index(
        "idx_conversation_messages_expires_at",
        table_name="conversation_messages",
    )
    op.drop_index(
        "idx_conversation_messages_run_id",
        table_name="conversation_messages",
    )
    op.drop_index(
        "idx_conversation_messages_thread_created_at",
        table_name="conversation_messages",
    )
    op.drop_index(
        "idx_conversation_messages_user_created_at",
        table_name="conversation_messages",
    )
    op.drop_table("conversation_messages")

    op.drop_index(
        "idx_agent_runs_expires_at",
        table_name="agent_runs",
    )
    op.drop_index(
        "idx_agent_runs_trace_id",
        table_name="agent_runs",
    )
    op.drop_index(
        "idx_agent_runs_user_started_at",
        table_name="agent_runs",
    )
    op.drop_index(
        "idx_agent_runs_thread_started_at",
        table_name="agent_runs",
    )
    op.drop_table("agent_runs")

    op.drop_index(
        "idx_conversation_threads_expires_at",
        table_name="conversation_threads",
    )
    op.drop_index(
        "idx_conversation_threads_status",
        table_name="conversation_threads",
    )
    op.drop_index(
        "idx_conversation_threads_user_updated_at",
        table_name="conversation_threads",
    )
    op.drop_table("conversation_threads")
