"""Scope-locked task evidence retrieval and safe citation projection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.recommendation.retrieval_pipeline import (
    RepositoryLexicalChannel,
    RepositoryVectorChannel,
    RetrievalPipeline,
    SearchRequest,
)
from app.ai_platform.models import ShoppingEvidencePublication
from sqlalchemy import select


class TaskQuerySpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: str = "task-query-spec.v1"
    original_question: str = Field(min_length=1, max_length=4000)
    subquestions: tuple[str, ...] = Field(default=(), max_length=3)
    evidence_type: str = Field(min_length=1, max_length=64)
    product_ids: tuple[str, ...] = Field(default=(), max_length=16)
    sku_codes: tuple[str, ...] = Field(default=(), max_length=16)
    category_code: str | None = None
    compatibility_keys: tuple[str, ...] = Field(default=(), max_length=16)
    policy_type: str | None = None
    region: str | None = None
    channel: str | None = None
    limit: int = Field(default=6, ge=1, le=20)
    rrf_k: int = Field(default=60, ge=1, le=1000)
    deadline_ms: int = Field(default=5000, ge=50, le=300000)

    @model_validator(mode="after")
    def keep_scope_immutable(self) -> "TaskQuerySpec":
        if any(not item.strip() for item in self.subquestions):
            raise ValueError("blank_subquestion")
        return self


class CitationProjection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    citation_id: str
    source_path: str | None = None
    evidence_type: str
    source_version: str | None = None
    status: str
    channel_attribution: tuple[str, ...] = ()
    product_ids: tuple[str, ...] = ()
    sku_codes: tuple[str, ...] = ()
    invalid_reason: str | None = None


class TaskEvidenceResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    status: str
    citations: list[CitationProjection] = Field(default_factory=list)
    channel_statuses: dict[str, str] = Field(default_factory=dict)
    supplemental_used: bool = False


def _citation(
    row: dict[str, Any], *, channels: tuple[str, ...]
) -> CitationProjection | None:
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    citation_id = row.get("id") or row.get("source_path")
    content = str(row.get("content") or "").casefold()
    injection_markers = (
        "ignore previous",
        "confirm_add_to_cart",
        "add_to_cart",
        "系统提示",
    )
    if (
        not citation_id
        or metadata.get("authority") not in {None, "evidence_only"}
        or metadata.get("status") in {"revoked", "expired", "failed"}
    ):
        return None
    if any(marker in content for marker in injection_markers):
        return None
    return CitationProjection(
        citation_id=str(citation_id),
        source_path=str(row.get("source_path")) if row.get("source_path") else None,
        evidence_type=str(
            row.get("evidence_type") or metadata.get("evidence_type") or "unknown"
        ),
        source_version=(
            str(metadata.get("version"))
            if metadata.get("version") is not None
            else None
        ),
        status=str(metadata.get("status") or "active"),
        channel_attribution=channels,
        product_ids=(
            tuple(str(item) for item in metadata.get("product_ids") or ())
            if isinstance(metadata.get("product_ids"), list)
            else ()
        ),
        sku_codes=(
            tuple(str(item) for item in metadata.get("sku_codes") or ())
            if isinstance(metadata.get("sku_codes"), list)
            else ()
        ),
    )


def retrieve_task_evidence(
    spec: TaskQuerySpec,
    *,
    session_factory: Callable,
    embed_query: Callable[[str], list[float]] | None = None,
    supplemental_query: str | None = None,
) -> TaskEvidenceResult:
    """Run the shared pipeline with at most three queries plus one supplement."""

    scope_session = session_factory()
    try:
        active_versions = tuple(
            scope_session.scalars(
                select(ShoppingEvidencePublication.evidence_version_id)
            ).all()
        )
    finally:
        scope_session.close()
    queries = [spec.original_question, *spec.subquestions[:2]]
    if supplemental_query:
        queries.append(supplemental_query)
    queries = queries[:4]
    channels = [RepositoryLexicalChannel(session_factory)]
    if embed_query is not None:
        channels.append(RepositoryVectorChannel(session_factory, embed_query))
    all_rows: list[dict[str, Any]] = []
    statuses: dict[str, str] = {}
    deadline = datetime.now(timezone.utc) + timedelta(milliseconds=spec.deadline_ms)
    for index, query in enumerate(queries):
        remaining = (deadline - datetime.now(timezone.utc)).total_seconds()
        if remaining <= 0:
            statuses[f"deadline:{index}"] = "timeout"
            break
        request = SearchRequest(
            query=query,
            evidence_type=spec.evidence_type,
            product_ids=spec.product_ids,
            category_code=spec.category_code,
            policy_type=spec.policy_type,
            region=spec.region,
            channel=spec.channel,
            limit=spec.limit,
            channel_timeout_seconds=min(2.0, remaining),
            rrf_k=spec.rrf_k,
            evidence_version_ids=active_versions,
        )
        rows, current = RetrievalPipeline(channels).search(request)
        all_rows.extend(rows)
        statuses.update({f"{name}:{index}": value for name, value in current.items()})
    seen: set[str] = set()
    projections: list[CitationProjection] = []
    for row in all_rows:
        key = str(row.get("id") or row.get("source_path") or "")
        if key in seen:
            continue
        seen.add(key)
        projection = _citation(
            row,
            channels=tuple(name for name in statuses if name.rsplit(":", 1)[-1] == "0"),
        )
        if projection is not None:
            if spec.sku_codes and (
                not projection.sku_codes
                or not set(spec.sku_codes).intersection(projection.sku_codes)
            ):
                continue
            projections.append(projection)
        if len(projections) >= spec.limit:
            break
    if projections:
        status = (
            "degraded"
            if any(
                value in {"degraded", "unavailable", "timeout"}
                for value in statuses.values()
            )
            else "ok"
        )
    elif any(value in {"unavailable", "timeout"} for value in statuses.values()):
        status = "unavailable"
    else:
        status = "empty"
    return TaskEvidenceResult(
        status=status,
        citations=projections,
        channel_statuses=statuses,
        supplemental_used=bool(supplemental_query),
    )


__all__ = [
    "CitationProjection",
    "TaskEvidenceResult",
    "TaskQuerySpec",
    "retrieve_task_evidence",
]
