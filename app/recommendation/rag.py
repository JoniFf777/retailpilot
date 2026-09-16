"""Post-ranking, whitelist-bound RAG evidence for structured recommendations."""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence

from app.db.session import SessionLocal
from app.repositories import documents as document_repository
from app.schemas.catalog import CatalogSkuCandidate
from app.schemas.recommendation import EvidenceView, RecommendationResult


_INJECTION_MARKERS = ("ignore previous", "add_to_cart", "confirm_add_to_cart", "系统提示")
_POLICY_TERMS = (
    "policy", "return", "refund", "warranty", "shipping",
    "退货", "退款", "保修", "配送", "政策",
)


@dataclass(frozen=True)
class RecommendationEvidence:
    product_evidence: dict[str, list[EvidenceView]]
    policy_evidence: list[EvidenceView]
    diagnostics: dict[str, object]


@dataclass(frozen=True)
class RetrievalBudget:
    """Independent limits for recall, fusion/rerank, and final context."""

    recall_per_scope: int = 2
    candidate_limit: int = 12
    context_per_candidate: int = 2
    subquestion_limit: int = 3
    channel_call_limit: int = 24

    def __post_init__(self) -> None:
        if min(
            self.recall_per_scope,
            self.candidate_limit,
            self.context_per_candidate,
            self.subquestion_limit,
            self.channel_call_limit,
        ) <= 0:
            raise ValueError("retrieval budgets must be positive")
        if self.candidate_limit < self.context_per_candidate:
            raise ValueError("candidate_limit must cover context_per_candidate")


class RecommendationEvidenceProvider(Protocol):
    def retrieve(
        self,
        *,
        message: str,
        top_k: Sequence[CatalogSkuCandidate],
    ) -> RecommendationEvidence: ...


class EvidenceReranker(Protocol):
    """Optional bounded post-fusion ranking contract."""

    def rerank(
        self, query: str, documents: Sequence[dict[str, object]], limit: int
    ) -> list[dict[str, object]]: ...


def build_retrieval_query_plan(message: str, *, limit: int = 3) -> dict[str, list[str]]:
    """Build bounded product/policy subquestions without rewriting constraints.

    The original request is always retained as the first query. Focused
    clauses are additive, so a query rewrite cannot remove a budget, exclusion,
    owner or explicit SKU from the trusted input.
    """

    limit = max(1, min(int(limit), 3))
    clauses = [part.strip() for part in re.split(r"[,，。；;\n]", message) if part.strip()]
    plans: dict[str, list[str]] = {"product": [], "policy": []}
    for scope, policy in (("product", False), ("policy", True)):
        selected = [
            clause
            for clause in clauses
            if any(term in clause.casefold() for term in _POLICY_TERMS) == policy
        ]
        queries = [message]
        for clause in selected:
            if clause not in queries:
                queries.append(clause)
            if len(queries) >= limit:
                break
        plans[scope] = queries[:limit]
    return plans


class LexicalEvidenceReranker:
    """Cheap deterministic reranker for local baselines and experiments."""

    def rerank(
        self, query: str, documents: Sequence[dict[str, object]], limit: int
    ) -> list[dict[str, object]]:
        terms = [
            term
            for term in re.findall(
                r"[A-Za-z0-9_-]+|[\u4e00-\u9fff]{2,}", query.casefold()
            )
            if term
        ]
        ranked: list[tuple[int, str, dict[str, object]]] = []
        for index, document in enumerate(documents):
            content = str(document.get("content") or "").casefold()
            overlap = sum(content.count(term) for term in terms)
            ranked.append((-overlap, str(document.get("id") or index), document))
        ranked.sort(key=lambda item: (item[0], item[1]))
        return [item[2] for item in ranked[:limit]]


class SemanticEvidenceReranker:
    """Lazy CrossEncoder reranker kept behind an explicit server setting."""

    def __init__(
        self,
        model_name: str,
        *,
        model_factory: Any | None = None,
        max_documents: int = 32,
        timeout_seconds: float = 3.0,
    ) -> None:
        self._model_name = model_name
        self._model_factory = model_factory
        self._max_documents = max(1, min(int(max_documents), 64))
        self._timeout_seconds = max(0.05, min(float(timeout_seconds), 30.0))
        self._model: Any | None = None

    def rerank(
        self, query: str, documents: Sequence[dict[str, object]], limit: int
    ) -> list[dict[str, object]]:
        if not documents or limit <= 0:
            return []
        if self._model is None:
            if self._model_factory is not None:
                self._model = self._model_factory(self._model_name)
            else:
                from sentence_transformers import CrossEncoder

                self._model = CrossEncoder(self._model_name)
        bounded_documents = list(documents[: self._max_documents])
        pairs = [(query, str(document.get("content") or "")) for document in bounded_documents]

        def predict() -> Any:
            return self._model.predict(pairs, show_progress_bar=False)

        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="shopmind-rerank")
        future = executor.submit(predict)
        try:
            scores = future.result(timeout=self._timeout_seconds)
        except FutureTimeoutError as exc:
            # A Python thread cannot be force-killed safely. Return on the
            # client deadline and let the bounded worker finish in isolation.
            executor.shutdown(wait=False, cancel_futures=True)
            raise TimeoutError("semantic reranker timed out") from exc
        else:
            executor.shutdown(wait=True)
        if len(scores) != len(bounded_documents):
            raise ValueError("semantic reranker returned an invalid score count")
        ranked = sorted(
            zip(scores, bounded_documents),
            key=lambda item: (-float(item[0]), str(item[1].get("id") or "")),
        )
        return [document for _, document in ranked[:limit]]


def _query_for_type(message: str, *, policy: bool) -> str:
    """Keep product and policy query clauses focused on their own intent."""

    clauses = [part.strip() for part in re.split(r"[,，。；;\n]", message) if part.strip()]
    selected = [
        clause
        for clause in clauses
        if any(term in clause.casefold() for term in _POLICY_TERMS) == policy
    ]
    return "，".join(selected) if selected else message


def _safe_excerpt(content: object, max_chars: int = 240, query: str | None = None) -> str:
    text = re.sub(r"\s+", " ", str(content or "")).strip()
    lowered = text.lower()
    if any(marker.lower() in lowered for marker in _INJECTION_MARKERS):
        return "Untrusted document content was excluded."
    if query and len(text) > max_chars:
        terms = [term for term in re.findall(r"[A-Za-z0-9_-]+|[\u4e00-\u9fff]{2,}", query.casefold()) if term]
        sentences = [part.strip() for part in re.split(r"(?<=[。！？.!?])\s*", text) if part.strip()]
        if terms and sentences:
            scored = sorted(
                enumerate(sentences),
                key=lambda item: (-sum(term in item[1].casefold() for term in terms), item[0]),
            )
            selected = sentences[scored[0][0]]
            if any(term in selected.casefold() for term in terms):
                return selected[:max_chars]
    return text[:max_chars]


def _evidence(
    document: dict[str, object], *, source: str, evidence_type: str, query: str | None = None
) -> EvidenceView:
    return EvidenceView(
        source=source,
        type=evidence_type,
        field="document_excerpt",
        value=_safe_excerpt(document.get("content"), query=query),
        ref=str(document.get("id")) if document.get("id") is not None else None,
        document_version=str(
            (document.get("metadata") or {}).get("document_version")
            or document.get("document_version")
        )
        if ((document.get("metadata") or {}).get("document_version") or document.get("document_version"))
        else None,
        section=str(
            (document.get("metadata") or {}).get("section_title")
            or document.get("section_title")
        )
        if ((document.get("metadata") or {}).get("section_title") or document.get("section_title"))
        else None,
    )


def _policy_scope(document: Mapping[str, object], allowed_product_ids: set[str]) -> str:
    """Return applicable/unknown/inapplicable from trusted policy metadata."""

    metadata = document.get("metadata") or {}
    if not isinstance(metadata, Mapping):
        metadata = {}
    raw_ids = metadata.get("product_ids") or metadata.get("applies_to_product_ids")
    if raw_ids is None:
        return "unknown"
    if isinstance(raw_ids, str):
        raw_ids = [raw_ids]
    if not isinstance(raw_ids, (list, tuple, set)):
        return "unknown"
    scoped_ids = {str(value) for value in raw_ids if value}
    return "applicable" if scoped_ids.intersection(allowed_product_ids) else "inapplicable"


def _select_current_policy_documents(
    documents: list[dict[str, object]], allowed_product_ids: set[str]
) -> tuple[list[dict[str, object]], int, int]:
    """Apply explicit scope and keep only the latest version per policy source."""

    applicable: list[dict[str, object]] = []
    inapplicable_count = 0
    for document in documents:
        scope = _policy_scope(document, allowed_product_ids)
        if scope == "inapplicable":
            inapplicable_count += 1
            continue
        applicable.append(document)
    grouped: dict[str, list[dict[str, object]]] = {}
    for document in applicable:
        metadata = document.get("metadata") or {}
        source_key = str(
            (metadata.get("policy_name") if isinstance(metadata, Mapping) else None)
            or document.get("policy_name")
            or document.get("source_path")
            or document.get("id")
        )
        grouped.setdefault(source_key, []).append(document)
    selected: list[dict[str, object]] = []
    version_conflicts = 0
    for records in grouped.values():
        versions = {
            str(
                ((record.get("metadata") or {}).get("document_version") if isinstance(record.get("metadata") or {}, Mapping) else None)
                or ""
            )
            for record in records
        }
        if len(versions - {""}) > 1:
            version_conflicts += 1
        current_version = max(versions) if versions - {""} else ""
        selected.extend(
            record
            for record in records
            if not current_version
            or str(
                ((record.get("metadata") or {}).get("document_version") if isinstance(record.get("metadata") or {}, Mapping) else None)
                or ""
            )
            == current_version
        )
    return selected, inapplicable_count, version_conflicts


class SqlAlchemyRecommendationEvidenceProvider:
    """Read evidence after Top K only; it never changes structured product facts."""

    def __init__(
        self,
        embed_query=None,
        reranker: EvidenceReranker | None = None,
        budget: RetrievalBudget | None = None,
    ) -> None:
        self._embed_query = embed_query
        self._reranker = reranker
        self._budget = budget or RetrievalBudget()

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
        query_plan = build_retrieval_query_plan(
            message, limit=self._budget.subquestion_limit
        )
        product_query = _query_for_type(message, policy=False)
        policy_query = _query_for_type(message, policy=True)
        legacy_ids = [candidate.legacy_product_id for candidate in top_k if candidate.legacy_product_id]
        policy_requested = any(
            keyword in message.casefold() for keyword in _POLICY_TERMS
        )
        product_vector_docs: list[dict[str, object]] = []
        product_keyword_docs: list[dict[str, object]] = []
        policy_vector_docs: list[dict[str, object]] = []
        policy_keyword_docs: list[dict[str, object]] = []
        product_vector_status = "not_applicable" if not legacy_ids else "empty"
        product_keyword_status = "not_applicable" if not legacy_ids else "empty"
        policy_vector_status = "not_requested" if not policy_requested else "empty"
        policy_keyword_status = "not_requested" if not policy_requested else "empty"
        channel_calls = 0
        with self._session() as session:
            if legacy_ids:
                vector_failures = 0
                embedding_failures = 0
                keyword_failures = 0
                for product_query_part in query_plan["product"]:
                    if channel_calls >= self._budget.channel_call_limit:
                        break
                    try:
                        product_embedding = self._embedding(product_query_part)
                        channel_calls += 1
                    except Exception:
                        product_embedding = None
                        product_vector_status = "unavailable"
                        embedding_failures += 1
                    if product_embedding is not None:
                        for legacy_id in sorted(set(legacy_ids)):
                            if channel_calls >= self._budget.channel_call_limit:
                                break
                            try:
                                product_vector_docs.extend(
                                    document_repository.search_product_documents_for_product_ids(
                                        session,
                                        product_embedding,
                                        product_ids=[legacy_id],
                                        k=self._budget.recall_per_scope,
                                    )
                                )
                                channel_calls += 1
                            except Exception:
                                session.rollback()
                                vector_failures += 1
                    if channel_calls >= self._budget.channel_call_limit:
                        break
                    try:
                        for legacy_id in sorted(set(legacy_ids)):
                            if channel_calls >= self._budget.channel_call_limit:
                                break
                            product_keyword_docs.extend(
                                document_repository.search_keyword_documents(
                                    session,
                                    product_query_part,
                                    doc_type="product",
                                    product_ids=[legacy_id],
                                    k=self._budget.recall_per_scope,
                                )
                            )
                            channel_calls += 1
                    except Exception:
                        session.rollback()
                        keyword_failures += 1
                product_vector_status = (
                    "degraded" if vector_failures and product_vector_docs
                    else "unavailable" if (vector_failures or embedding_failures) and not product_vector_docs
                    else "degraded" if embedding_failures
                    else "ok" if product_vector_docs
                    else "empty"
                )
                product_keyword_status = (
                    "degraded" if keyword_failures and product_keyword_docs
                    else "unavailable" if keyword_failures and not product_keyword_docs
                    else "ok" if product_keyword_docs
                    else "empty"
                )
            if policy_requested:
                policy_vector_failures = 0
                policy_keyword_failures = 0
                for policy_query_part in query_plan["policy"]:
                    if channel_calls >= self._budget.channel_call_limit:
                        break
                    try:
                        policy_vector_docs.extend(
                            document_repository.search_policy_documents(
                                session,
                                self._embedding(policy_query_part),
                                k=self._budget.candidate_limit,
                            )
                        )
                        channel_calls += 1
                    except Exception:
                        session.rollback()
                        policy_vector_failures += 1
                    if channel_calls >= self._budget.channel_call_limit:
                        break
                    try:
                        policy_keyword_docs.extend(
                            document_repository.search_keyword_documents(
                                session,
                                policy_query_part,
                                doc_type="policy",
                                k=self._budget.candidate_limit,
                            )
                        )
                        channel_calls += 1
                    except Exception:
                        session.rollback()
                        policy_keyword_failures += 1
                policy_vector_status = (
                    "degraded" if policy_vector_failures and policy_vector_docs
                    else "unavailable" if policy_vector_failures and not policy_vector_docs
                    else "ok" if policy_vector_docs
                    else "empty"
                )
                policy_keyword_status = (
                    "degraded" if policy_keyword_failures and policy_keyword_docs
                    else "unavailable" if policy_keyword_failures and not policy_keyword_docs
                    else "ok" if policy_keyword_docs
                    else "empty"
                )

        def fuse(vector_docs: list[dict[str, object]], keyword_docs: list[dict[str, object]], limit: int) -> list[dict[str, object]]:
            records: dict[str, dict[str, object]] = {}
            scores: dict[str, float] = {}
            for docs in (vector_docs, keyword_docs):
                for rank, document in enumerate(docs, start=1):
                    key = str(document.get("id") or f"{document.get('source_path') or 'anonymous'}:{document.get('chunk_index') or rank}")
                    records.setdefault(key, document)
                    scores[key] = scores.get(key, 0.0) + 1.0 / (60.0 + rank)
            return [
                records[key]
                for key in sorted(records, key=lambda item: (-scores[item], item))[:limit]
            ]

        product_docs = fuse(
            product_vector_docs,
            product_keyword_docs,
            min(self._budget.candidate_limit, max(1, len(legacy_ids) * self._budget.recall_per_scope * 2)),
        )
        policy_docs = fuse(policy_vector_docs, policy_keyword_docs, self._budget.candidate_limit)
        policy_docs, policy_inapplicable_count, policy_version_conflicts = (
            _select_current_policy_documents(policy_docs, set(legacy_ids))
        )
        reranker_status = "disabled"
        if self._reranker is not None:
            reranker_status = "degraded"

            def safe_rerank(
                query: str,
                documents: list[dict[str, object]],
                limit: int,
            ) -> list[dict[str, object]]:
                proposed = self._reranker.rerank(query, documents, limit)
                allowed_by_key = {
                    str(document.get("id") or f"{document.get('source_path') or 'anonymous'}:{document.get('chunk_index') or index}"): document
                    for index, document in enumerate(documents, start=1)
                }
                allowed = set(allowed_by_key)
                seen: set[str] = set()
                selected: list[dict[str, object]] = []
                invalid_output = False
                for index, document in enumerate(proposed, start=1):
                    key = str(document.get("id") or f"{document.get('source_path') or 'anonymous'}:{document.get('chunk_index') or index}")
                    if key in allowed and key not in seen:
                        # Keep the original fused object. A reranker may return
                        # a score or a copied dict, but it cannot replace the
                        # trusted document body under an existing ID.
                        selected.append(allowed_by_key[key])
                        seen.add(key)
                    elif key not in allowed:
                        invalid_output = True
                for index, document in enumerate(documents, start=1):
                    key = str(document.get("id") or f"{document.get('source_path') or 'anonymous'}:{document.get('chunk_index') or index}")
                    if key not in seen:
                        selected.append(document)
                        seen.add(key)
                if invalid_output or len(selected) < min(limit, len(documents)):
                    raise ValueError("reranker returned an invalid document subset")
                return selected[:limit]

            try:
                product_docs = safe_rerank(
                    product_query, product_docs, self._budget.candidate_limit
                )
                if policy_requested:
                    policy_docs = safe_rerank(
                        policy_query, policy_docs, self._budget.candidate_limit
                    )
                reranker_status = "ok"
            except Exception:
                # A broken optional reranker cannot remove valid fused evidence.
                reranker_status = "degraded"
        requested_statuses = [
            status
            for status in (
                product_vector_status,
                product_keyword_status,
                policy_vector_status,
                policy_keyword_status,
            )
            if status not in {"not_applicable", "not_requested"}
        ]
        if product_docs or policy_docs:
            evidence_status = "available"
        elif requested_statuses and all(status == "unavailable" for status in requested_statuses):
            evidence_status = "unavailable"
        elif "unavailable" in requested_statuses:
            evidence_status = "degraded"
        else:
            evidence_status = "unknown"
        allowed = set(legacy_ids)
        grouped: dict[str, list[EvidenceView]] = {candidate.sku_code: [] for candidate in top_k}
        by_legacy: dict[str, list[str]] = {}
        for candidate in top_k:
            if candidate.legacy_product_id:
                by_legacy.setdefault(candidate.legacy_product_id, []).append(candidate.sku_code)
        for document in product_docs:
            product_id = str(document.get("product_id") or "")
            if product_id in allowed and product_id in by_legacy:
                for sku_code in by_legacy[product_id]:
                    if len(grouped[sku_code]) < self._budget.context_per_candidate:
                        grouped[sku_code].append(
                            _evidence(
                                document,
                                source="product_rag",
                                evidence_type="product_document",
                                query=message,
                            )
                        )
        return RecommendationEvidence(
            product_evidence=grouped,
            policy_evidence=[
                _evidence(
                    document,
                    source="policy_rag",
                    evidence_type="policy_document",
                    query=message,
                )
                for document in policy_docs
            ],
            diagnostics={
                "requested_legacy_product_ids": sorted(allowed),
                "product_vector_count": len(product_vector_docs),
                "product_keyword_count": len(product_keyword_docs),
                "product_vector_status": product_vector_status,
                "product_keyword_status": product_keyword_status,
                "product_document_count": len(product_docs),
                "policy_requested": policy_requested,
                "policy_vector_count": len(policy_vector_docs),
                "policy_keyword_count": len(policy_keyword_docs),
                "policy_vector_status": policy_vector_status,
                "policy_keyword_status": policy_keyword_status,
                "policy_document_count": len(policy_docs),
                "policy_inapplicable_count": policy_inapplicable_count,
                "policy_version_conflicts": policy_version_conflicts,
                "evidence_status": evidence_status,
                "fusion": "rrf",
                "product_retrieval_scope": "per_legacy_product",
                "reranker": (
                    self._reranker.__class__.__name__ if self._reranker is not None else None
                ),
                "reranker_status": reranker_status,
                "retrieval_budget": {
                    "recall_per_scope": self._budget.recall_per_scope,
                    "candidate_limit": self._budget.candidate_limit,
                    "context_per_candidate": self._budget.context_per_candidate,
                    "subquestion_limit": self._budget.subquestion_limit,
                    "channel_call_limit": self._budget.channel_call_limit,
                    "channel_calls_used": channel_calls,
                },
                "query_plan": query_plan,
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
