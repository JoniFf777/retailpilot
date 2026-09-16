"""Document repository functions backed by SQLAlchemy sessions."""

from __future__ import annotations

import math
import re
from typing import Any, Sequence

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.models import Document


MAX_KEYWORD_CORPUS_DOCUMENTS = 2_000
MAX_KEYWORD_DOCUMENT_CHARS = 12_000


def _keyword_tokens(value: str) -> list[str]:
    """Return stable Latin/SKU terms and Chinese phrase bigrams.

    This intentionally small in-process index is suitable for the bounded
    ShopMind catalog.  It is a lexical recall channel, not a claim that
    PostgreSQL's vector distance or a substring match is BM25.
    """

    tokens: list[str] = []
    for part in re.findall(r"[a-z0-9][a-z0-9_-]*|[\u4e00-\u9fff]+", value.casefold()):
        tokens.append(part)
        if re.fullmatch(r"[\u4e00-\u9fff]+", part) and len(part) > 2:
            tokens.extend(part[index : index + 2] for index in range(len(part) - 1))
    return tokens


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


def search_product_documents_for_product_ids(
    session: Session,
    query_embedding: Sequence[float],
    *,
    product_ids: Sequence[str],
    k: int = 6,
) -> list[dict[str, Any]]:
    """Search only the explicit legacy-product whitelist selected by Catalog.

    This is deliberately not a natural-language product-ID extraction path.  A
    candidate with no legacy mapping simply has no product-document evidence.
    """

    normalized_ids = sorted({str(product_id) for product_id in product_ids if product_id})
    if not normalized_ids:
        return []
    bind = session.get_bind()
    if bind.dialect.name != "postgresql":
        statement = (
            select(Document)
            .where(Document.doc_type == "product", Document.product_id.in_(normalized_ids))
            .order_by(Document.product_id.asc(), Document.id.asc())
            .limit(k)
        )
        return [document_to_dict(document) for document in session.scalars(statement).all()]

    embedding = _format_pgvector(query_embedding)
    statement = text(
        """
        SELECT id, doc_type, source_path, source_name, product_id, product_name,
               policy_name, chunk_index, content, metadata_json,
               embedding_provider, embedding_model,
               embedding <=> CAST(:embedding AS vector) AS distance
        FROM documents
        WHERE doc_type = 'product' AND product_id = ANY(:product_ids)
        ORDER BY embedding <=> CAST(:embedding AS vector), id ASC
        LIMIT :k
        """
    )
    rows = session.execute(
        statement,
        {"embedding": embedding, "product_ids": normalized_ids, "k": k},
    ).mappings()
    return [_row_to_dict(row) for row in rows]


def search_policy_documents(
    session: Session,
    query_embedding: Sequence[float],
    k: int = 2,
) -> list[dict[str, Any]]:
    return search_documents(
        session, query_embedding, doc_type="policy", k=k
    )


def search_keyword_documents(
    session: Session,
    query: str,
    *,
    doc_type: str,
    product_ids: Sequence[str] | None = None,
    k: int = 10,
) -> list[dict[str, Any]]:
    """Run a bounded BM25-style lexical search over the active document rows.

    The corpus is deliberately loaded through the same owner/category filters
    as vector search.  This keeps exact SKU/model terms recoverable without
    introducing a second search service or allowing lexical search to widen
    the trusted scope.
    """

    if k <= 0:
        return []
    statement = select(Document).where(Document.doc_type == doc_type)
    normalized_ids = sorted({str(value) for value in (product_ids or []) if value})
    if product_ids is not None and not normalized_ids:
        return []
    if normalized_ids:
        statement = statement.where(Document.product_id.in_(normalized_ids))
    documents = list(
        session.scalars(statement.limit(MAX_KEYWORD_CORPUS_DOCUMENTS)).all()
    )
    query_terms = _keyword_tokens(query)
    if not documents or not query_terms:
        return []

    tokenized = [
        _keyword_tokens((document.content or "")[:MAX_KEYWORD_DOCUMENT_CHARS])
        for document in documents
    ]
    document_frequency: dict[str, int] = {}
    for terms in tokenized:
        for term in set(terms):
            document_frequency[term] = document_frequency.get(term, 0) + 1
    average_length = sum(len(terms) for terms in tokenized) / max(1, len(tokenized))
    query_frequency: dict[str, int] = {}
    for term in query_terms:
        query_frequency[term] = query_frequency.get(term, 0) + 1

    scored: list[tuple[float, Document]] = []
    for document, terms in zip(documents, tokenized):
        term_frequency: dict[str, int] = {}
        for term in terms:
            term_frequency[term] = term_frequency.get(term, 0) + 1
        length = len(terms)
        score = 0.0
        for term, query_count in query_frequency.items():
            frequency = term_frequency.get(term, 0)
            if not frequency:
                continue
            document_count = document_frequency.get(term, 0)
            idf = math.log(1 + (len(documents) - document_count + 0.5) / (document_count + 0.5))
            denominator = frequency + 1.2 * (1 - 0.75 + 0.75 * length / max(1.0, average_length))
            score += idf * (frequency * 2.2 / denominator) * min(query_count, 2)
        if score > 0:
            scored.append((score, document))
    scored.sort(key=lambda item: (-item[0], item[1].id))
    return [document_to_dict(document, score=score) for score, document in scored[:k]]
