"""add shopping evidence ingestion lifecycle tables

Revision ID: 0016_shopping_evidence_pipeline
Revises: 0015_shopmind_order_expiration
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0016_shopping_evidence_pipeline"
down_revision: Union[str, None] = "0015_shopmind_order_expiration"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "shopmind_evidence_versions",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("evidence_key", sa.String(length=160), nullable=False),
        sa.Column("evidence_type", sa.String(length=32), nullable=False),
        sa.Column("source_path", sa.Text(), nullable=False),
        sa.Column("source_name", sa.String(length=255)),
        sa.Column("source_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("content_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("product_ids", sa.JSON(), nullable=False),
        sa.Column("sku_codes", sa.JSON(), nullable=False),
        sa.Column("category_code", sa.String(length=64)),
        sa.Column("compatibility_keys", sa.JSON(), nullable=False),
        sa.Column("policy_type", sa.String(length=64)),
        sa.Column("region", sa.String(length=64)),
        sa.Column("channel", sa.String(length=64)),
        sa.Column("valid_from", sa.DateTime(timezone=True)),
        sa.Column("valid_until", sa.DateTime(timezone=True)),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="processing"),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "evidence_type IN ('product_guide', 'compatibility', 'buying_guide', 'store_policy')",
            name="ck_shopmind_evidence_type",
        ),
        sa.CheckConstraint(
            "status IN ('processing', 'published', 'failed', 'revoked')",
            name="ck_shopmind_evidence_status",
        ),
        sa.CheckConstraint("version >= 1", name="ck_shopmind_evidence_version_positive"),
    )
    op.create_index("idx_shopmind_evidence_scope", "shopmind_evidence_versions", ["evidence_type", "category_code", "policy_type"])
    op.create_index("idx_shopmind_evidence_source", "shopmind_evidence_versions", ["source_fingerprint", "content_fingerprint"])
    op.create_index("idx_shopmind_evidence_validity", "shopmind_evidence_versions", ["policy_type", "valid_from", "valid_until"])

    op.create_table(
        "shopmind_evidence_ingestion_tasks",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("evidence_version_id", sa.BigInteger(), sa.ForeignKey("shopmind_evidence_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("current_node", sa.String(length=16)),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("lease_owner", sa.String(length=128)),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_error_code", sa.String(length=64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('pending', 'running', 'completed', 'failed', 'cancelled')", name="ck_shopmind_ingestion_task_status"),
        sa.CheckConstraint("attempt_count >= 0", name="ck_shopmind_ingestion_attempts_nonnegative"),
        sa.UniqueConstraint("idempotency_key", name="uq_shopmind_ingestion_idempotency"),
    )
    op.create_index("idx_shopmind_ingestion_claim", "shopmind_evidence_ingestion_tasks", ["status", "lease_until", "available_at"])

    op.create_table(
        "shopmind_evidence_ingestion_nodes",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("task_id", sa.BigInteger(), sa.ForeignKey("shopmind_evidence_ingestion_tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("node_type", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_fingerprint", sa.String(length=64)),
        sa.Column("item_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(length=64)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("node_type IN ('fetcher', 'parser', 'chunker', 'enricher', 'indexer')", name="ck_shopmind_ingestion_node_type"),
        sa.CheckConstraint("status IN ('pending', 'running', 'completed', 'failed', 'skipped')", name="ck_shopmind_ingestion_node_status"),
        sa.UniqueConstraint("task_id", "node_type", name="uq_shopmind_ingestion_task_node"),
    )

    op.create_table(
        "shopmind_evidence_publications",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("evidence_key", sa.String(length=160), nullable=False),
        sa.Column("evidence_version_id", sa.BigInteger(), sa.ForeignKey("shopmind_evidence_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("evidence_key", name="uq_shopmind_evidence_publication_key"),
        sa.UniqueConstraint("evidence_version_id", name="uq_shopmind_evidence_publication_version"),
    )


def downgrade() -> None:
    op.drop_table("shopmind_evidence_publications")
    op.drop_table("shopmind_evidence_ingestion_nodes")
    op.drop_index("idx_shopmind_ingestion_claim", table_name="shopmind_evidence_ingestion_tasks")
    op.drop_table("shopmind_evidence_ingestion_tasks")
    op.drop_index("idx_shopmind_evidence_validity", table_name="shopmind_evidence_versions")
    op.drop_index("idx_shopmind_evidence_source", table_name="shopmind_evidence_versions")
    op.drop_index("idx_shopmind_evidence_scope", table_name="shopmind_evidence_versions")
    op.drop_table("shopmind_evidence_versions")
