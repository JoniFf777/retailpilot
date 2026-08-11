"""Post-ranking, whitelist-bound RAG evidence for structured recommendations."""

from __future__ import annotations

import re
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Mapping, Protocol, Sequence

from app.db.session import SessionLocal
from app.repositories import documents as document_repository
from app.schemas.catalog import CatalogSkuCandidate
from app.schemas.recommendation import EvidenceView, RecommendationResult


_INJECTION_MARKERS = ("ignore previous", "add_to_cart", "confirm_add_to_cart", "系统提示")


@dataclass(frozen=True)
class RecommendationEvidence:
    product_evidence: dict[str, list[EvidenceView]]
    policy_evidence: list[EvidenceView]
    diagnostics: dict[str, object]


class RecommendationEvidenceProvider(Protocol):
    def retrieve(
        self,
        *,
        message: str,
        top_k: Sequence[CatalogSkuCandidate],
    ) -> RecommendationEvidence: ...


def _safe_excerpt(content: object, max_chars: int = 240) -> str:
    text = re.sub(r"\s+", " ", str(content or "")).strip()
    lowered = text.lower()
    if any(marker.lower() in lowered for marker in _INJECTION_MARKERS):
        return "Untrusted document content was excluded."
    return text[:max_chars]


def _evidence(document: dict[str, object], *, source: str, evidence_type: str) -> EvidenceView:
    return EvidenceView(
        source=source,
        type=evidence_type,
        field="document_excerpt",
        value=_safe_excerpt(document.get("content")),
        ref=str(document.get("id")) if document.get("id") is not None else None,
    )


class SqlAlchemyRecommendationEvidenceProvider:
    """Read evidence after Top K only; it never changes structured product facts."""

    def __init__(self, embed_query=None) -> None:
        self._embed_query = embed_query

    @contextmanager
    def _session(self):
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    def _embedding(self, message: str) -> Sequence[float]:
        if self._embed_query is not None:
            return self._embed_query(message)
        from tools.documents import _embed_query

        return _embed_query(message)

    def retrieve(
        self,
        *,
        message: str,
        top_k: Sequence[CatalogSkuCandidate],
    ) -> RecommendationEvidence:
        embedding = self._embedding(message)
        legacy_ids = [candidate.legacy_product_id for candidate in top_k if candidate.legacy_product_id]
        with self._session() as session:
            product_docs = document_repository.search_product_documents_for_product_ids(
                session, embedding, product_ids=legacy_ids, k=max(1, len(legacy_ids) * 2)
            )
            policy_docs = document_repository.search_policy_documents(session, embedding, k=2)
        allowed = set(legacy_ids)
        grouped: dict[str, list[EvidenceView]] = {candidate.sku_code: [] for candidate in top_k}
        by_legacy = {candidate.legacy_product_id: candidate.sku_code for candidate in top_k if candidate.legacy_product_id}
        for document in product_docs:
            product_id = str(document.get("product_id") or "")
            if product_id in allowed and product_id in by_legacy:
                grouped[by_legacy[product_id]].append(
                    _evidence(document, source="product_rag", evidence_type="product_document")
                )
        return RecommendationEvidence(
            product_evidence=grouped,
            policy_evidence=[_evidence(document, source="policy_rag", evidence_type="policy_document") for document in policy_docs],
            diagnostics={
                "requested_legacy_product_ids": sorted(allowed),
                "product_document_count": len(product_docs),
                "policy_document_count": len(policy_docs),
            },
        )


class FakeRecommendationEvidenceProvider:
    def __init__(self, evidence: RecommendationEvidence | None = None) -> None:
        self.evidence = evidence or RecommendationEvidence({}, [], {})
        self.calls: list[list[str]] = []

    def retrieve(self, *, message: str, top_k: Sequence[CatalogSkuCandidate]) -> RecommendationEvidence:
        del message
        self.calls.append([candidate.sku_code for candidate in top_k])
        return self.evidence


class OfflineDemoRecommendationEvidenceProvider:
    """Server-owned no-network evidence boundary for the offline demo.

    Structured catalog facts and ranking still come from PostgreSQL.  The
    optional document-evidence enrichment is intentionally empty so the core
    demo never downloads or initializes an embedding model.
    """

    def retrieve(
        self,
        *,
        message: str,
        top_k: Sequence[CatalogSkuCandidate],
    ) -> RecommendationEvidence:
        del message
        return RecommendationEvidence(
            product_evidence={candidate.sku_code: [] for candidate in top_k},
            policy_evidence=[],
            diagnostics={
                "offline_demo": True,
                "document_evidence_skipped": True,
            },
        )


def attach_validated_evidence(
    result: RecommendationResult,
    evidence: RecommendationEvidence,
    *,
    sku_codes_by_id: Mapping[object, str],
) -> RecommendationResult:
    """Attach only evidence for existing Top-K SKUs; no evidence may add a SKU."""

    if result.outcome != "recommended":
        return result
    recommendations = []
    for recommendation in result.recommendations:
        recommendations.append(
            recommendation.model_copy(
                update={
                    "evidence": evidence.product_evidence.get(
                        sku_codes_by_id.get(recommendation.sku_id, ""), []
                    )
                }
            )
        )
    return result.model_copy(update={"recommendations": recommendations})
