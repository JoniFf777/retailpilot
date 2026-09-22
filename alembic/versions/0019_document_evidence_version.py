"""associate indexed documents with versioned shopping evidence

Revision ID: 0019_document_evidence_version
Revises: 0018_shopping_task_workbench
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0019_document_evidence_version"
down_revision: Union[str, None] = "0018_shopping_task_workbench"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "documents", sa.Column("evidence_version_id", sa.BigInteger(), nullable=True)
    )
    op.create_foreign_key(
        "fk_documents_evidence_version",
        "documents",
        "shopmind_evidence_versions",
        ["evidence_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "idx_documents_evidence_version", "documents", ["evidence_version_id"]
    )


def downgrade() -> None:
    op.drop_index("idx_documents_evidence_version", table_name="documents")
    op.drop_constraint("fk_documents_evidence_version", "documents", type_="foreignkey")
    op.drop_column("documents", "evidence_version_id")
