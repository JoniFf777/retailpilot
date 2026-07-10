"""create candidate contexts table

Revision ID: 0003_candidate_contexts
Revises: 0002_documents_pgvector
Create Date: 2026-07-10 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0003_candidate_contexts"
down_revision: Union[str, None] = "0002_documents_pgvector"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "candidate_contexts",
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("thread_id", sa.String(), nullable=False),
        sa.Column("product_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
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
            "quantity > 0",
            name="ck_candidate_contexts_quantity_positive",
        ),
        sa.PrimaryKeyConstraint("user_id", "thread_id"),
    )
    op.create_index(
        "idx_candidate_contexts_expires_at",
        "candidate_contexts",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_candidate_contexts_expires_at",
        table_name="candidate_contexts",
    )
    op.drop_table("candidate_contexts")
