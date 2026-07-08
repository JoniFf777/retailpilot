"""Document repository functions backed by SQLAlchemy sessions."""

from __future__ import annotations

from typing import Any, Sequence

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.models import Document


def _format_pgvector(values: Sequence[float]) -> str:
    return "[" + ",".join(str(value) for value in values) + "]"


def document_to_dict(document: Document, score: float | None = None) -> dict[str, Any]:
    result = {
        "id": document.id,
        "doc_type": document.doc_type,
        "source_path": document.source_path,
        "source_name": document.source_name,
        "product_id": document.product_id,
        "product_name": document.product_name,
        "policy_name": document.policy_name,
        "chunk_index": document.chunk_index,
        "content": document.content,
        "metadata": document.metadata_json,
        "embedding_provider": document.embedding_provider,
        "embedding_model": document.embedding_model,
    }
    if score is not None:
        result["score"] = score
    return result


def _row_to_dict(row: Any) -> dict[str, Any]:
    def get_value(key: str) -> Any:
        if isinstance(row, dict):
            return row.get(key)
        try:
            return row[key]
        except (KeyError, TypeError):
            return getattr(row, key)

    metadata = get_value("metadata_json") or {}
    result = {
        "id": get_value("id"),
        "doc_type": get_value("doc_type"),
        "source_path": get_value("source_path"),
        "source_name": get_value("source_name"),
        "product_id": get_value("product_id"),
        "product_name": get_value("product_name"),
        "policy_name": get_value("policy_name"),
        "chunk_index": get_value("chunk_index"),
        "content": get_value("content"),
        "metadata": metadata,
        "embedding_provider": get_value("embedding_provider"),
        "embedding_model": get_value("embedding_model"),
    }
    distance = get_value("distance")
    if distance is not None:
        result["score"] = float(distance)
    return result


def _search_documents_sqlite(
    session: Session,
    *,
    doc_type: str,
    k: int,
) -> list[dict[str, Any]]:
    statement = (
        select(Document)
        .where(Document.doc_type == doc_type)
        .order_by(Document.id.asc())
        .limit(k)
    )
    return [
        document_to_dict(document)
        for document in session.scalars(statement).all()
    ]


def search_documents(
    session: Session,
    query_embedding: Sequence[float],
    *,
    doc_type: str,
    k: int,
) -> list[dict[str, Any]]:
    """Search documents by pgvector cosine distance.

    SQLite test sessions use a deterministic fallback because SQLite does not
    support pgvector operators.
    """
    bind = session.get_bind()
    if bind.dialect.name != "postgresql":
        return _search_documents_sqlite(session, doc_type=doc_type, k=k)

    embedding = _format_pgvector(query_embedding)
    statement = text(
        """
        SELECT
            id,
            doc_type,
            source_path,
            source_name,
            product_id,
            product_name,
            policy_name,
            chunk_index,
            content,
            metadata_json,
            embedding_provider,
            embedding_model,
            embedding <=> CAST(:embedding AS vector) AS distance
        FROM documents
        WHERE doc_type = :doc_type
        ORDER BY embedding <=> CAST(:embedding AS vector)
        LIMIT :k
        """
    )
    rows = session.execute(
        statement,
        {"embedding": embedding, "doc_type": doc_type, "k": k},
    ).mappings()
    return [_row_to_dict(row) for row in rows]


def search_product_documents(
    session: Session,
    query_embedding: Sequence[float],
    k: int = 3,
) -> list[dict[str, Any]]:
    return search_documents(
        session, query_embedding, doc_type="product", k=k
    )


def search_policy_documents(
    session: Session,
    query_embedding: Sequence[float],
    k: int = 2,
) -> list[dict[str, Any]]:
    return search_documents(
        session, query_embedding, doc_type="policy", k=k
    )
