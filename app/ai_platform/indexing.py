"""Adapters from shopping evidence chunks to the existing pgvector table."""

from __future__ import annotations

from typing import Any, Callable

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.ai_platform.contracts import EvidenceType, ShoppingEvidenceDescriptor
from app.ai_platform.guards import non_authoritative_document_metadata
from app.ai_platform.ingestion import EvidenceChunk
from app.db.models import Document


def _value(value: Any) -> str:
    return str(getattr(value, "value", value))


class PostgreSQLEvidenceIndexer:
    """Write a source atomically into the legacy document search table."""

    def __init__(
        self,
        session: Session,
        embeddings: Any,
        *,
        embedding_provider: str,
        embedding_model: str,
    ) -> None:
        self._session = session
        self._embeddings = embeddings
        self._embedding_provider = embedding_provider
        self._embedding_model = embedding_model

    def index(
        self,
        chunks: list[EvidenceChunk],
        descriptor: ShoppingEvidenceDescriptor,
        *,
        evidence_version_id: int | None = None,
    ) -> int:
        vectors = self._embeddings.embed_documents([chunk.content for chunk in chunks])
        if len(vectors) != len(chunks):
            raise ValueError("Embedding count does not match evidence chunk count.")
        if evidence_version_id is not None:
            self._session.execute(
                delete(Document).where(
                    Document.evidence_version_id == evidence_version_id
                )
            )
        doc_type = (
            "policy"
            if descriptor.evidence_type
            in {
                EvidenceType.STORE_POLICY.value,
                EvidenceType.COMPATIBILITY.value,
            }
            else "product"
        )
        for chunk, vector in zip(chunks, vectors):
            metadata = non_authoritative_document_metadata(
                {
                    **chunk.metadata,
                    "evidence_type": _value(descriptor.evidence_type),
                    "product_ids": list(descriptor.scope.product_ids),
                    "sku_codes": list(descriptor.scope.sku_codes),
                    "category_code": descriptor.scope.category_code,
                    "policy_type": descriptor.scope.policy_type,
                    "region": descriptor.scope.region,
                    "channel": descriptor.scope.channel,
                    "valid_from": (
                        descriptor.scope.valid_from.isoformat()
                        if descriptor.scope.valid_from
                        else None
                    ),
                    "valid_until": (
                        descriptor.scope.valid_until.isoformat()
                        if descriptor.scope.valid_until
                        else None
                    ),
                    "document_version": descriptor.content_fingerprint[:16],
                    "evidence_version_id": evidence_version_id,
                }
            )
            self._session.add(
                Document(
                    doc_type=doc_type,
                    evidence_version_id=evidence_version_id,
                    source_path=descriptor.source_path,
                    source_name=descriptor.source_name,
                    product_id=(
                        descriptor.scope.product_ids[0]
                        if descriptor.scope.product_ids
                        else None
                    ),
                    product_name=descriptor.title,
                    policy_name=descriptor.scope.policy_type,
                    chunk_index=chunk.index,
                    content=chunk.content,
                    metadata_json=metadata,
                    embedding="[" + ",".join(str(value) for value in vector) + "]",
                    embedding_provider=self._embedding_provider,
                    embedding_model=self._embedding_model,
                )
            )
        self._session.flush()
        return len(chunks)


class FakeEvidenceIndexer:
    """Deterministic indexer for contract and pipeline tests."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def index(
        self, chunks: list[EvidenceChunk], descriptor: ShoppingEvidenceDescriptor
    ) -> int:
        self.calls.append((descriptor.source_path, len(chunks)))
        return len(chunks)


__all__ = ["FakeEvidenceIndexer", "PostgreSQLEvidenceIndexer"]
