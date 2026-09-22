"""add server-owned shopping AI extension registry

Revision ID: 0017_ai_extension_registry
Revises: 0016_shopping_evidence_pipeline
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0017_ai_extension_registry"
down_revision: Union[str, None] = "0016_shopping_evidence_pipeline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("ck_governance_audit_operation", "governance_audit_records", type_="check")
    op.create_check_constraint(
        "ck_governance_audit_operation",
        "governance_audit_records",
        "operation IN ("
        "'authentication.bind', 'tool.invoke', "
        "'action.prepare', 'action.resume', 'action.confirm', "
        "'action.cancel', 'action.expire', "
        "'memory.create', 'memory.inspect', 'memory.correct', 'memory.delete', "
        "'deletion.request', 'deletion.execute', "
        "'admin.extension.publish', 'admin.evidence.revoke')",
    )
    op.create_table(
        "shopmind_ai_extension_definitions",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("extension_type", sa.String(length=16), nullable=False),
        sa.Column("extension_key", sa.String(length=128), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("capability", sa.String(length=64), nullable=False),
        sa.Column("agent_names", sa.JSON(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("tool_ids", sa.JSON(), nullable=False),
        sa.Column("side_effect", sa.String(length=16), nullable=False, server_default="none"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="draft"),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("activated_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("extension_type IN ('prompt', 'skill', 'mcp_tool')", name="ck_shopmind_ai_extension_type"),
        sa.CheckConstraint("status IN ('draft', 'active', 'revoked')", name="ck_shopmind_ai_extension_status"),
        sa.UniqueConstraint("extension_type", "extension_key", "version", name="uq_shopmind_ai_extension_version"),
    )
    op.create_index("idx_shopmind_ai_extension_active", "shopmind_ai_extension_definitions", ["extension_type", "extension_key", "status"])
    op.create_table(
        "shopmind_ai_extension_publications",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("extension_type", sa.String(length=16), nullable=False),
        sa.Column("extension_key", sa.String(length=128), nullable=False),
        sa.Column("definition_id", sa.BigInteger(), sa.ForeignKey("shopmind_ai_extension_definitions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("extension_type", "extension_key", name="uq_shopmind_ai_extension_publication"),
    )


def downgrade() -> None:
    op.drop_table("shopmind_ai_extension_publications")
    op.drop_index("idx_shopmind_ai_extension_active", table_name="shopmind_ai_extension_definitions")
    op.drop_table("shopmind_ai_extension_definitions")
    op.drop_constraint("ck_governance_audit_operation", "governance_audit_records", type_="check")
    op.create_check_constraint(
        "ck_governance_audit_operation",
        "governance_audit_records",
        "operation IN ("
        "'authentication.bind', 'tool.invoke', "
        "'action.prepare', 'action.resume', 'action.confirm', "
        "'action.cancel', 'action.expire', "
        "'memory.create', 'memory.inspect', 'memory.correct', 'memory.delete', "
        "'deletion.request', 'deletion.execute')",
    )
