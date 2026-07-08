"""create documents pgvector table

Revision ID: 0002_documents_pgvector
Revises: 0001_structured_tables
Create Date: 2026-07-07 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op


revision: str = "0002_documents_pgvector"
down_revision: Union[str, None] = "0001_structured_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        """
        CREATE TABLE documents (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            doc_type text NOT NULL,
            source_path text NOT NULL,
            source_name text,
            product_id text,
            product_name text,
            policy_name text,
            chunk_index integer NOT NULL,
            content text NOT NULL,
            metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
            embedding vector(768) NOT NULL,
            embedding_provider text NOT NULL,
            embedding_model text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_documents_doc_type
                CHECK (doc_type IN ('product', 'policy'))
        )
        """
    )
    op.execute("CREATE INDEX idx_documents_doc_type ON documents (doc_type)")
    op.execute("CREATE INDEX idx_documents_product_id ON documents (product_id)")
    op.execute("CREATE INDEX idx_documents_source_path ON documents (source_path)")
    op.execute(
        "CREATE INDEX idx_documents_metadata_json "
        "ON documents USING gin (metadata_json)"
    )
    op.execute(
        "CREATE INDEX idx_documents_embedding_hnsw "
        "ON documents USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_documents_embedding_hnsw")
    op.execute("DROP INDEX IF EXISTS idx_documents_metadata_json")
    op.execute("DROP INDEX IF EXISTS idx_documents_source_path")
    op.execute("DROP INDEX IF EXISTS idx_documents_product_id")
    op.execute("DROP INDEX IF EXISTS idx_documents_doc_type")
    op.execute("DROP TABLE IF EXISTS documents")
