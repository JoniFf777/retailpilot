"""Shopping-specific document ingestion pipeline."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Protocol

from sqlalchemy.orm import Session

from app.ai_platform.contracts import (
    EvidenceScope,
    EvidenceType,
    PipelineNodeType,
    ShoppingEvidenceDescriptor,
)
from app.ai_platform.guards import non_authoritative_document_metadata
from app.repositories.shopping_evidence import (
    create_ingestion_task,
    mark_node_completed,
    mark_node_running,
    publish_evidence_version,
)
from app.ai_platform.models import ShoppingIngestionTask


MAX_SOURCE_CHARS = 200_000
MAX_CHUNKS = 500
MAX_CHUNK_CHARS = 2_000


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))


class ShoppingEvidencePipelineError(ValueError):
    """Stable, safe pipeline failure."""


@dataclass(frozen=True)
class EvidenceChunk:
    content: str
    index: int
    metadata: dict[str, Any]


class EvidenceIndexer(Protocol):
    def index(
        self, chunks: list[EvidenceChunk], descriptor: ShoppingEvidenceDescriptor
    ) -> int: ...


@dataclass(frozen=True)
class PipelineRunResult:
    task_id: int
    evidence_version_id: int
    status: str
    chunk_count: int


def fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def classify_legacy_source(
    path: str | Path, content: str
) -> ShoppingEvidenceDescriptor:
    source_path = str(path)
    name = Path(source_path).stem.casefold()
    source_fingerprint = fingerprint(source_path)
    content_fingerprint = fingerprint(content)
    if len(content) > MAX_SOURCE_CHARS:
        raise ShoppingEvidencePipelineError("source_too_large")
    if "/products/" in source_path.replace("\\", "/"):
        evidence_type = EvidenceType.PRODUCT_GUIDE
        scope = EvidenceScope(product_ids=(Path(source_path).stem,))
    elif name == "compatibility_guide":
        evidence_type = EvidenceType.COMPATIBILITY
        scope = EvidenceScope(compatibility_keys=("catalog_compatibility",))
    else:
        evidence_type = EvidenceType.STORE_POLICY
        scope = EvidenceScope(policy_type=name)
    return ShoppingEvidenceDescriptor(
        evidence_type=evidence_type,
        source_path=source_path,
        source_name=Path(source_path).name,
        source_fingerprint=source_fingerprint,
        content_fingerprint=content_fingerprint,
        scope=scope,
        title=_title(content),
        metadata=non_authoritative_document_metadata(
            {
                "legacy_doc_type": (
                    "product"
                    if evidence_type == EvidenceType.PRODUCT_GUIDE
                    else "policy"
                )
            }
        ),
    )


def _title(content: str) -> str | None:
    for line in content.splitlines():
        if line.startswith("# "):
            return line[2:].strip()[:512]
    return None


def parse_markdown(content: str) -> str:
    normalized = content.replace("\x00", "").strip()
    if not normalized:
        raise ShoppingEvidencePipelineError("empty_source")
    return normalized


def chunk_markdown(content: str, *, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    if max_chars <= 0 or max_chars > MAX_CHUNK_CHARS:
        raise ValueError("Invalid chunk size.")
    paragraphs = [
        part.strip() for part in re.split(r"\n\s*\n", content) if part.strip()
    ]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(paragraph) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(
                paragraph[index : index + max_chars]
                for index in range(0, len(paragraph), max_chars)
            )
            continue
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) > max_chars and current:
            chunks.append(current)
            current = paragraph
        else:
            current = candidate
    if current:
        chunks.append(current)
    if len(chunks) > MAX_CHUNKS:
        raise ShoppingEvidencePipelineError("too_many_chunks")
    return chunks


class ShoppingEvidencePipeline:
    """Run the five nodes synchronously; persistence makes the run resumable."""

    def __init__(
        self,
        indexer: EvidenceIndexer | None = None,
        *,
        known_product_ids: set[str] | None = None,
        known_categories: set[str] | None = None,
    ) -> None:
        self._indexer = indexer
        self._known_product_ids = known_product_ids
        self._known_categories = known_categories

    def run(
        self,
        session: Session,
        descriptor: ShoppingEvidenceDescriptor,
        content: str,
        *,
        idempotency_key: str | None = None,
        now: datetime | None = None,
    ) -> PipelineRunResult:
        validate_descriptor_against_catalog(
            descriptor,
            known_product_ids=self._known_product_ids,
            known_categories=self._known_categories,
        )
        task = create_ingestion_task(
            session,
            descriptor,
            idempotency_key=idempotency_key or descriptor.content_fingerprint,
        )
        if task.status == "completed":
            index_node = next(
                (
                    node
                    for node in task.nodes
                    if node.node_type == PipelineNodeType.INDEXER.value
                ),
                None,
            )
            return PipelineRunResult(
                task_id=task.id,
                evidence_version_id=task.evidence_version_id,
                status=task.status,
                chunk_count=index_node.item_count if index_node else 0,
            )
        try:
            return self._run(
                session,
                task,
                descriptor,
                content,
                now=now,
            )
        except Exception:
            from app.repositories.shopping_evidence import mark_task_failed

            mark_task_failed(session, task, error_code="pipeline_failed", now=now)
            raise

    def _run(
        self,
        session: Session,
        task: ShoppingIngestionTask,
        descriptor: ShoppingEvidenceDescriptor,
        content: str,
        *,
        now: datetime | None = None,
    ) -> PipelineRunResult:
        session.flush()
        normalized = parse_markdown(content)
        chunks: list[EvidenceChunk] = []
        node_by_type = {node.node_type: node for node in task.nodes}

        task.current_node = PipelineNodeType.FETCHER.value
        mark_node_running(
            session, node_by_type[PipelineNodeType.FETCHER.value], now=now
        )
        mark_node_completed(
            session,
            node_by_type[PipelineNodeType.FETCHER.value],
            output_fingerprint=descriptor.content_fingerprint,
            item_count=1,
            now=now,
        )
        task.current_node = PipelineNodeType.PARSER.value
        mark_node_running(session, node_by_type[PipelineNodeType.PARSER.value], now=now)
        parsed = parse_markdown(normalized)
        mark_node_completed(
            session,
            node_by_type[PipelineNodeType.PARSER.value],
            output_fingerprint=fingerprint(parsed),
            item_count=1,
            now=now,
        )
        task.current_node = PipelineNodeType.CHUNKER.value
        mark_node_running(
            session, node_by_type[PipelineNodeType.CHUNKER.value], now=now
        )
        raw_chunks = chunk_markdown(parsed)
        chunks = [
            EvidenceChunk(
                content=value,
                index=index,
                metadata={
                    "evidence_type": _enum_value(descriptor.evidence_type),
                    "source_path": descriptor.source_path,
                    "content_fingerprint": descriptor.content_fingerprint,
                    "chunk_index": index,
                    **descriptor.metadata,
                },
            )
            for index, value in enumerate(raw_chunks)
        ]
        mark_node_completed(
            session,
            node_by_type[PipelineNodeType.CHUNKER.value],
            output_fingerprint=fingerprint("\n".join(raw_chunks)),
            item_count=len(chunks),
            now=now,
        )
        task.current_node = PipelineNodeType.ENRICHER.value
        mark_node_running(
            session, node_by_type[PipelineNodeType.ENRICHER.value], now=now
        )
        enriched = [
            EvidenceChunk(
                content=chunk.content,
                index=chunk.index,
                metadata={
                    **chunk.metadata,
                    "scope": descriptor.scope.model_dump(mode="json"),
                    "authority": "evidence_only",
                },
            )
            for chunk in chunks
        ]
        mark_node_completed(
            session,
            node_by_type[PipelineNodeType.ENRICHER.value],
            output_fingerprint=fingerprint(
                "\n".join(chunk.content for chunk in enriched)
            ),
            item_count=len(enriched),
            now=now,
        )
        task.current_node = PipelineNodeType.INDEXER.value
        mark_node_running(
            session, node_by_type[PipelineNodeType.INDEXER.value], now=now
        )
        if self._indexer:
            try:
                indexed = self._indexer.index(
                    enriched, descriptor, evidence_version_id=task.evidence_version_id
                )
            except TypeError as exc:
                if "evidence_version_id" not in str(exc):
                    raise
                indexed = self._indexer.index(enriched, descriptor)
        else:
            indexed = len(enriched)
        if indexed != len(enriched):
            raise ShoppingEvidencePipelineError("index_count_mismatch")
        mark_node_completed(
            session,
            node_by_type[PipelineNodeType.INDEXER.value],
            output_fingerprint=fingerprint(
                "\n".join(chunk.content for chunk in enriched)
            ),
            item_count=indexed,
            now=now,
        )
        published = publish_evidence_version(session, task, now=now)
        return PipelineRunResult(
            task_id=task.id,
            evidence_version_id=published.id,
            status=task.status,
            chunk_count=indexed,
        )


def load_legacy_sources(
    documents_dir: Path,
) -> list[tuple[ShoppingEvidenceDescriptor, str]]:
    result: list[tuple[ShoppingEvidenceDescriptor, str]] = []
    for path in sorted((documents_dir / "products").glob("*.md")):
        content = path.read_text(encoding="utf-8")
        result.append((classify_legacy_source(path, content), content))
    for path in sorted((documents_dir / "policies").glob("*.md")):
        content = path.read_text(encoding="utf-8")
        result.append((classify_legacy_source(path, content), content))
    return result


def validate_descriptor_against_catalog(
    descriptor: ShoppingEvidenceDescriptor,
    *,
    known_product_ids: set[str] | None = None,
    known_categories: set[str] | None = None,
) -> None:
    """Validate references when a caller provides a trusted Catalog snapshot."""

    if known_product_ids is not None:
        missing = set(descriptor.scope.product_ids).difference(known_product_ids)
        if missing:
            raise ShoppingEvidencePipelineError("dangling_product_reference")
    if known_categories is not None and descriptor.scope.category_code:
        if descriptor.scope.category_code not in known_categories:
            raise ShoppingEvidencePipelineError("unknown_category_reference")


__all__ = [
    "EvidenceChunk",
    "PipelineRunResult",
    "ShoppingEvidencePipeline",
    "ShoppingEvidencePipelineError",
    "classify_legacy_source",
    "chunk_markdown",
    "fingerprint",
    "load_legacy_sources",
    "parse_markdown",
    "validate_descriptor_against_catalog",
]
