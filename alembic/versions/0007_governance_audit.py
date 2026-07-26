"""add PII-safe governance audit persistence

Revision ID: 0007_governance_audit
Revises: 0006_action_registry_fields
Create Date: 2026-07-26 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0007_governance_audit"
down_revision: Union[str, None] = "0006_action_registry_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "governance_audit_records",
        sa.Column("audit_id", sa.String(length=36), nullable=False),
        sa.Column("schema_version", sa.String(length=64), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("operation", sa.String(length=64), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.String(length=64), nullable=False),
        sa.Column("actor_kind", sa.String(length=32), nullable=False),
        sa.Column("actor_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("owner_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("thread_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("run_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("resource_fingerprint", sa.String(length=64), nullable=True),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "schema_version = 'shopmind.governance-audit.v1'",
            name="ck_governance_audit_schema_version",
        ),
        sa.CheckConstraint(
            "category IN ('authentication', 'tool', 'action', 'memory', 'deletion')",
            name="ck_governance_audit_category",
        ),
        sa.CheckConstraint(
            "operation IN ("
            "'authentication.bind', 'tool.invoke', "
            "'action.prepare', 'action.resume', 'action.confirm', "
            "'action.cancel', 'action.expire', "
            "'memory.create', 'memory.inspect', 'memory.correct', 'memory.delete', "
            "'deletion.request', 'deletion.execute'"
            ")",
            name="ck_governance_audit_operation",
        ),
        sa.CheckConstraint(
            "decision IN ("
            "'allowed', 'denied', 'requested', 'succeeded', "
            "'failed', 'skipped', 'not_found'"
            ")",
            name="ck_governance_audit_decision",
        ),
        sa.CheckConstraint(
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
        sa.CheckConstraint(
            "actor_kind IN ('principal', 'system', 'anonymous')",
            name="ck_governance_audit_actor_kind",
        ),
        sa.CheckConstraint(
            "actor_fingerprint IS NULL OR length(actor_fingerprint) = 64",
            name="ck_governance_audit_actor_fingerprint",
        ),
        sa.CheckConstraint(
            "owner_fingerprint IS NULL OR length(owner_fingerprint) = 64",
            name="ck_governance_audit_owner_fingerprint",
        ),
        sa.CheckConstraint(
            "thread_fingerprint IS NULL OR length(thread_fingerprint) = 64",
            name="ck_governance_audit_thread_fingerprint",
        ),
        sa.CheckConstraint(
            "run_fingerprint IS NULL OR length(run_fingerprint) = 64",
            name="ck_governance_audit_run_fingerprint",
        ),
        sa.CheckConstraint(
            "resource_fingerprint IS NULL OR length(resource_fingerprint) = 64",
            name="ck_governance_audit_resource_fingerprint",
        ),
        sa.CheckConstraint(
            "expires_at > occurred_at",
            name="ck_governance_audit_retention_window",
        ),
        sa.PrimaryKeyConstraint("audit_id"),
    )
    op.create_index(
        "idx_governance_audit_owner_occurred_at",
        "governance_audit_records",
        ["owner_fingerprint", "occurred_at"],
    )
    op.create_index(
        "idx_governance_audit_category_occurred_at",
        "governance_audit_records",
        ["category", "occurred_at"],
    )
    op.create_index(
        "idx_governance_audit_run_occurred_at",
        "governance_audit_records",
        ["run_fingerprint", "occurred_at"],
    )
    op.create_index(
        "idx_governance_audit_resource",
        "governance_audit_records",
        ["resource_fingerprint"],
    )
    op.create_index(
        "idx_governance_audit_expires_at",
        "governance_audit_records",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_governance_audit_expires_at",
        table_name="governance_audit_records",
    )
    op.drop_index(
        "idx_governance_audit_resource",
        table_name="governance_audit_records",
    )
    op.drop_index(
        "idx_governance_audit_run_occurred_at",
        table_name="governance_audit_records",
    )
    op.drop_index(
        "idx_governance_audit_category_occurred_at",
        table_name="governance_audit_records",
    )
    op.drop_index(
        "idx_governance_audit_owner_occurred_at",
        table_name="governance_audit_records",
    )
    op.drop_table("governance_audit_records")
