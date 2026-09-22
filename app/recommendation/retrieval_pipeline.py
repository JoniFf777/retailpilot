"""Business-scoped retrieval channels and deterministic post-processors."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Protocol

from app.repositories import documents as document_repository


@dataclass(frozen=True)
class SearchRequest:
    query: str
    evidence_type: str
    product_ids: tuple[str, ...] = ()
    category_code: str | None = None
    policy_type: str | None = None
    region: str | None = None
    channel: str | None = None
    limit: int = 10
    channel_timeout_seconds: float = 10.0
    rrf_k: int = 20
    evidence_version_ids: tuple[int, ...] | None = None

    def __post_init__(self) -> None:
        if not self.query.strip():
            raise ValueError("Search query cannot be blank.")
        if self.limit <= 0:
            raise ValueError("Search limit must be positive.")
        if self.channel_timeout_seconds <= 0:
            raise ValueError("Search timeout must be positive.")
        if self.rrf_k <= 0:
            raise ValueError("RRF k must be positive.")


class SearchChannel(Protocol):
    name: str

    def search(self, request: SearchRequest) -> list[dict[str, Any]]: ...


class RepositoryVectorChannel:
    """Vector channel over the existing PostgreSQL/SQLite evidence repository."""

    def __init__(
        self,
        session_factory: Callable,
        embed_query: Callable[[str], list[float]],
        name: str = "vector",
    ) -> None:
        self._session_factory = session_factory
        self._embed_query = embed_query
        self.name = name

    def search(self, request: SearchRequest) -> list[dict[str, Any]]:
        session = self._session_factory()
        try:
            embedding = self._embed_query(request.query)
            if request.product_ids:
                rows = document_repository.search_product_documents_for_product_ids(
                    session,
                    embedding,
                    product_ids=request.product_ids,
                    evidence_version_ids=request.evidence_version_ids,
                    k=request.limit,
                )
            elif request.evidence_type == "store_policy":
                rows = document_repository.search_policy_documents(
                    session,
                    embedding,
                    evidence_version_ids=request.evidence_version_ids,
                    k=request.limit,
                )
            else:
                rows = document_repository.search_documents(
                    session,
                    embedding,
                    doc_type=(
                        "policy"
                        if request.evidence_type == "compatibility"
                        else "product"
                    ),
                    k=request.limit,
                    evidence_version_ids=request.evidence_version_ids,
                )
            return [_with_evidence_type(row, request.evidence_type) for row in rows]
        finally:
            session.close()


class RepositoryLexicalChannel:
    """Lexical channel over the same scope and repository as vector search."""

    def __init__(self, session_factory: Callable, name: str = "lexical") -> None:
        self._session_factory = session_factory
        self.name = name

    def search(self, request: SearchRequest) -> list[dict[str, Any]]:
        session = self._session_factory()
        try:
            rows = document_repository.search_keyword_documents(
                session,
                request.query,
                doc_type=(
                    "policy"
                    if request.evidence_type in {"compatibility", "store_policy"}
                    else "product"
                ),
                product_ids=request.product_ids if request.product_ids else None,
                k=request.limit,
                evidence_version_ids=request.evidence_version_ids,
            )
            return [_with_evidence_type(row, request.evidence_type) for row in rows]
        finally:
            session.close()


class DisabledExternalChannel:
    """Explicit no-op for graph/web channels until a server enables them."""

    def __init__(self, name: str) -> None:
        if name not in {"graph", "web_search"}:
            raise ValueError(
                "Only graph and web_search are optional external channels."
            )
        self.name = name

    def search(self, request: SearchRequest) -> list[dict[str, Any]]:
        del request
        return []


def _with_evidence_type(value: dict[str, Any], evidence_type: str) -> dict[str, Any]:
    result = dict(value)
    metadata = dict(result.get("metadata") or {})
    metadata.setdefault("evidence_type", evidence_type)
    metadata.setdefault("authority", "evidence_only")
    if result.get("product_id"):
        metadata.setdefault("product_ids", [result["product_id"]])
    result["metadata"] = metadata
    result["evidence_type"] = evidence_type
    return result


class PostProcessor(Protocol):
    name: str

    def process(
        self, candidates: list[dict[str, Any]], request: SearchRequest
    ) -> list[dict[str, Any]]: ...


def normalize_candidates(
    candidates: list[dict[str, Any]], request: SearchRequest
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    allowed_products = set(request.product_ids)
    for item in candidates:
        value = dict(item)
        metadata = value.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}
        if (
            str(metadata.get("evidence_type") or value.get("evidence_type") or "")
            != request.evidence_type
        ):
            continue
        scoped_products = set(metadata.get("product_ids") or ())
        product_id = value.get("product_id") or metadata.get("product_id")
        if (
            allowed_products
            and scoped_products
            and not allowed_products.intersection(
                scoped_products | {str(product_id or "")}
            )
        ):
            continue
        value["metadata"] = metadata
        value.setdefault("evidence_type", request.evidence_type)
        normalized.append(value)
    return normalized


def deduplicate_candidates(
    candidates: list[dict[str, Any]], request: SearchRequest
) -> list[dict[str, Any]]:
    del request
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for item in candidates:
        key = str(item.get("id") or item.get("source_path") or item.get("content", ""))
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def rrf_fuse(
    ranked_lists: list[list[dict[str, Any]]],
    *,
    limit: int,
    rrf_k: int = 20,
) -> list[dict[str, Any]]:
    if limit <= 0 or rrf_k <= 0:
        return []
    fused: dict[str, dict[str, Any]] = {}
    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, item in enumerate(ranked, start=1):
            key = str(
                item.get("id") or item.get("source_path") or item.get("content", "")
            )
            fused.setdefault(key, dict(item))
            scores[key] = scores.get(key, 0.0) + 1.0 / (rrf_k + rank)
    ordered = sorted(fused, key=lambda key: (-scores[key], key))[:limit]
    result: list[dict[str, Any]] = []
    for key in ordered:
        item = fused[key]
        item["rrf_score"] = scores[key]
        result.append(item)
    return result


class EvidenceGate:
    name = "evidence_gate"

    def process(
        self, candidates: list[dict[str, Any]], request: SearchRequest
    ) -> list[dict[str, Any]]:
        allowed_products = set(request.product_ids)
        result: list[dict[str, Any]] = []
        for item in candidates:
            metadata = item.get("metadata") or {}
            if metadata.get("authority") not in {None, "evidence_only"}:
                continue
            if allowed_products:
                scoped = set(metadata.get("product_ids") or ())
                product_id = str(
                    item.get("product_id") or metadata.get("product_id") or ""
                )
                # A scoped recommendation query cannot trust a legacy chunk
                # that lacks product identity; accepting it would let an old
                # un-migrated document masquerade as evidence for any SKU.
                if not scoped and not product_id:
                    continue
                if not allowed_products.intersection(scoped | {product_id}):
                    continue
            if request.policy_type and metadata.get("policy_type") not in {
                None,
                request.policy_type,
            }:
                continue
            if request.region and metadata.get("region") not in {None, request.region}:
                continue
            if request.channel and metadata.get("channel") not in {
                None,
                request.channel,
            }:
                continue
            now = datetime.now(timezone.utc)
            valid_from = metadata.get("valid_from")
            valid_until = metadata.get("valid_until")
            try:
                parsed_from = (
                    datetime.fromisoformat(str(valid_from).replace("Z", "+00:00"))
                    if valid_from
                    else None
                )
                parsed_until = (
                    datetime.fromisoformat(str(valid_until).replace("Z", "+00:00"))
                    if valid_until
                    else None
                )
            except ValueError:
                continue
            if parsed_from and parsed_from.tzinfo is None:
                parsed_from = parsed_from.replace(tzinfo=timezone.utc)
            if parsed_until and parsed_until.tzinfo is None:
                parsed_until = parsed_until.replace(tzinfo=timezone.utc)
            if parsed_from and parsed_from > now:
                continue
            if parsed_until and parsed_until <= now:
                continue
            result.append(item)
        return result[: request.limit]


class RerankPostProcessor:
    """Validate a reranker's ID subset and retain trusted original documents."""

    name = "rerank"

    def __init__(
        self, reranker: Callable[[str, list[dict[str, Any]], int], list[Any]]
    ) -> None:
        self._reranker = reranker

    def process(
        self, candidates: list[dict[str, Any]], request: SearchRequest
    ) -> list[dict[str, Any]]:
        proposed = self._reranker(request.query, candidates, request.limit)
        by_key = {
            str(
                item.get("id") or item.get("source_path") or item.get("content", "")
            ): item
            for item in candidates
        }
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in proposed:
            key = str(item.get("id") if isinstance(item, dict) else item)
            if key not in by_key or key in seen:
                raise ValueError("reranker returned an invalid document subset")
            result.append(by_key[key])
            seen.add(key)
        result.extend(item for key, item in by_key.items() if key not in seen)
        return result[: request.limit]


class RetrievalPipeline:
    """Execute independent channels, then a fixed safe post-processing chain."""

    def __init__(
        self,
        channels: list[SearchChannel],
        *,
        post_processors: list[PostProcessor] | None = None,
        executor: ThreadPoolExecutor | None = None,
    ) -> None:
        self._channels = tuple(channels)
        self._post_processors = tuple(post_processors or [EvidenceGate()])
        self._executor = executor

    def search(
        self, request: SearchRequest
    ) -> tuple[list[dict[str, Any]], dict[str, str]]:
        statuses: dict[str, str] = {}
        futures = []
        executor = self._executor or ThreadPoolExecutor(
            max_workers=max(1, len(self._channels))
        )
        owns_executor = self._executor is None
        try:
            for channel in self._channels:
                futures.append((channel, executor.submit(channel.search, request)))
            ranked: list[list[dict[str, Any]]] = []
            for channel, future in futures:
                try:
                    values = future.result(timeout=request.channel_timeout_seconds)
                except FutureTimeoutError:
                    statuses[channel.name] = "degraded"
                    continue
                except Exception:
                    statuses[channel.name] = "unavailable"
                    continue
                statuses[channel.name] = "ok" if values else "empty"
                ranked.append(normalize_candidates(values, request))
            candidates = rrf_fuse(ranked, limit=request.limit, rrf_k=request.rrf_k)
            candidates = deduplicate_candidates(candidates, request)
            for processor in self._post_processors:
                try:
                    candidates = processor.process(candidates, request)
                except Exception:
                    statuses[processor.name] = "degraded"
            return candidates[: request.limit], statuses
        finally:
            if owns_executor:
                executor.shutdown(wait=False, cancel_futures=True)


__all__ = [
    "EvidenceGate",
    "DisabledExternalChannel",
    "PostProcessor",
    "RerankPostProcessor",
    "RepositoryLexicalChannel",
    "RetrievalPipeline",
    "RepositoryVectorChannel",
    "SearchChannel",
    "SearchRequest",
    "deduplicate_candidates",
    "normalize_candidates",
    "rrf_fuse",
]
