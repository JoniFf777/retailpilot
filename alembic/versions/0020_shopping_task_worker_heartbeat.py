"""Add durable shopping task worker heartbeat.

Revision ID: 0020_task_worker_heartbeat
Revises: 0019_document_evidence_version
"""

from alembic import op
import sqlalchemy as sa


revision = "0020_task_worker_heartbeat"
down_revision = "0019_document_evidence_version"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "shopmind_shopping_task_worker_heartbeats",
        sa.Column("worker_id", sa.String(length=128), primary_key=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "idx_shopmind_task_worker_last_seen",
        "shopmind_shopping_task_worker_heartbeats",
        ["last_seen_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_shopmind_task_worker_last_seen",
        table_name="shopmind_shopping_task_worker_heartbeats",
    )
    op.drop_table("shopmind_shopping_task_worker_heartbeats")
