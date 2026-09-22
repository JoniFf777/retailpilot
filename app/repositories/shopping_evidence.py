"""Persistence helpers for the shopping-evidence lifecycle."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.ai_platform.contracts import (
    EvidenceScope,
    PipelineNodeType,
    ShoppingEvidenceDescriptor,
)
from app.ai_platform.models import (
    ShoppingEvidencePublication,
    ShoppingEvidenceVersion,
    ShoppingIngestionNode,
    ShoppingIngestionTask,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))


def _scope_json(scope: EvidenceScope) -> dict[str, Any]:
    return {
        "product_ids": list(scope.product_ids),
        "sku_codes": list(scope.sku_codes),
        "category_code": scope.category_code,
        "compatibility_keys": list(scope.compatibility_keys),
        "policy_type": scope.policy_type,
        "region": scope.region,
        "channel": scope.channel,
        "valid_from": scope.valid_from.isoformat() if scope.valid_from else None,
        "valid_until": scope.valid_until.isoformat() if scope.valid_until else None,
    }


def create_ingestion_task(
    session: Session,
    descriptor: ShoppingEvidenceDescriptor,
    *,
    idempotency_key: str,
    max_attempts: int = 3,
) -> ShoppingIngestionTask:
    existing = session.scalar(
        select(ShoppingIngestionTask).where(
            ShoppingIngestionTask.idempotency_key == idempotency_key
        )
    )
    if existing is not None:
        return existing
    previous_version = (
        session.scalar(
            select(func.max(ShoppingEvidenceVersion.version)).where(
                ShoppingEvidenceVersion.evidence_key == descriptor.source_path
            )
        )
        or 0
    )
    evidence = ShoppingEvidenceVersion(
        evidence_key=descriptor.source_path,
        evidence_type=_enum_value(descriptor.evidence_type),
        source_path=descriptor.source_path,
        source_name=descriptor.source_name,
        source_fingerprint=descriptor.source_fingerprint,
        content_fingerprint=descriptor.content_fingerprint,
        product_ids=list(descriptor.scope.product_ids),
        sku_codes=list(descriptor.scope.sku_codes),
        category_code=descriptor.scope.category_code,
        compatibility_keys=list(descriptor.scope.compatibility_keys),
        policy_type=descriptor.scope.policy_type,
        region=descriptor.scope.region,
        channel=descriptor.scope.channel,
        valid_from=descriptor.scope.valid_from,
        valid_until=descriptor.scope.valid_until,
        version=previous_version + 1,
        metadata_json={**descriptor.metadata, "scope": _scope_json(descriptor.scope)},
    )
    session.add(evidence)
    session.flush()
    task = ShoppingIngestionTask(
        evidence_version_id=evidence.id,
        idempotency_key=idempotency_key,
        max_attempts=max_attempts,
    )
    session.add(task)
    session.flush()
    for node_type in PipelineNodeType:
        session.add(ShoppingIngestionNode(task_id=task.id, node_type=node_type.value))
    session.flush()
    return task


def get_ingestion_task(session: Session, task_id: int) -> ShoppingIngestionTask | None:
    return session.scalar(
        select(ShoppingIngestionTask).where(ShoppingIngestionTask.id == task_id)
    )


def claim_ingestion_tasks(
    session: Session,
    *,
    worker_id: str | None = None,
    limit: int = 10,
    lease_seconds: int = 60,
    now: datetime | None = None,
) -> list[ShoppingIngestionTask]:
    now = now or _now()
    worker_id = worker_id or uuid4().hex
    statement = (
        select(ShoppingIngestionTask)
        .where(
            ShoppingIngestionTask.status.in_(("pending", "running")),
            ShoppingIngestionTask.available_at <= now,
            (
                ShoppingIngestionTask.lease_until.is_(None)
                | (ShoppingIngestionTask.lease_until < now)
            ),
        )
        .order_by(ShoppingIngestionTask.created_at, ShoppingIngestionTask.id)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    tasks = list(session.scalars(statement).all())
    for task in tasks:
        task.status = "running"
        task.attempt_count += 1
        task.lease_owner = worker_id
        task.lease_until = now + timedelta(seconds=lease_seconds)
    session.flush()
    return tasks


def mark_node_running(
    session: Session, node: ShoppingIngestionNode, *, now: datetime | None = None
) -> None:
    node.status = "running"
    node.attempt_count += 1
    node.started_at = now or _now()
    session.flush()


def mark_node_completed(
    session: Session,
    node: ShoppingIngestionNode,
    *,
    output_fingerprint: str | None = None,
    item_count: int = 0,
    now: datetime | None = None,
) -> None:
    node.status = "completed"
    node.output_fingerprint = output_fingerprint
    node.item_count = item_count
    node.error_code = None
    node.completed_at = now or _now()
    session.flush()


def mark_task_failed(
    session: Session,
    task: ShoppingIngestionTask,
    *,
    error_code: str,
    now: datetime | None = None,
) -> None:
    task.status = "failed" if task.attempt_count >= task.max_attempts else "pending"
    task.last_error_code = error_code
    task.lease_owner = None
    task.lease_until = None
    task.available_at = (now or _now()) + timedelta(seconds=5)
    evidence = task.evidence_version
    if task.current_node:
        for node in task.nodes:
            if node.node_type == task.current_node and node.status == "running":
                node.status = "failed"
                node.error_code = error_code
                node.completed_at = now or _now()
    if task.status == "failed":
        evidence.status = "failed"
    session.flush()


def publish_evidence_version(
    session: Session,
    task: ShoppingIngestionTask,
    *,
    now: datetime | None = None,
) -> ShoppingEvidenceVersion:
    now = now or _now()
    if any(node.status != "completed" for node in task.nodes):
        raise ValueError("All ingestion nodes must complete before publication.")
    evidence = task.evidence_version
    evidence.status = "published"
    evidence.published_at = now
    task.status = "completed"
    task.current_node = None
    task.lease_owner = None
    task.lease_until = None
    task.completed_at = now
    session.flush()
    current = session.scalar(
        select(ShoppingEvidencePublication).where(
            ShoppingEvidencePublication.evidence_key == evidence.evidence_key
        )
    )
    if current is None:
        current = ShoppingEvidencePublication(
            evidence_key=evidence.evidence_key,
            evidence_version_id=evidence.id,
            published_at=now,
        )
        session.add(current)
    else:
        current.evidence_version_id = evidence.id
        current.published_at = now
    session.flush()
    return evidence


def revoke_evidence(session: Session, evidence_key: str) -> bool:
    publication = session.scalar(
        select(ShoppingEvidencePublication).where(
            ShoppingEvidencePublication.evidence_key == evidence_key
        )
    )
    if publication is None:
        return False
    evidence = session.get(ShoppingEvidenceVersion, publication.evidence_version_id)
    if evidence is not None:
        evidence.status = "revoked"
    session.delete(publication)
    session.flush()
    return True


def list_current_evidence(
    session: Session,
    *,
    evidence_type: str | None = None,
    category_code: str | None = None,
    product_ids: list[str] | None = None,
    policy_type: str | None = None,
    now: datetime | None = None,
    limit: int = 100,
) -> list[ShoppingEvidenceVersion]:
    now = now or _now()
    statement = (
        select(ShoppingEvidenceVersion)
        .join(
            ShoppingEvidencePublication,
            ShoppingEvidencePublication.evidence_version_id
            == ShoppingEvidenceVersion.id,
        )
        .where(ShoppingEvidenceVersion.status == "published")
        .where(
            (
                ShoppingEvidenceVersion.valid_from.is_(None)
                | (ShoppingEvidenceVersion.valid_from <= now)
            ),
            (
                ShoppingEvidenceVersion.valid_until.is_(None)
                | (ShoppingEvidenceVersion.valid_until > now)
            ),
        )
        .order_by(ShoppingEvidenceVersion.id)
        .limit(limit)
    )
    if evidence_type:
        statement = statement.where(
            ShoppingEvidenceVersion.evidence_type == evidence_type
        )
    if category_code:
        statement = statement.where(
            ShoppingEvidenceVersion.category_code == category_code
        )
    if policy_type:
        statement = statement.where(ShoppingEvidenceVersion.policy_type == policy_type)
    rows = list(session.scalars(statement).all())
    if product_ids is not None:
        wanted = set(product_ids)
        rows = [row for row in rows if wanted.intersection(set(row.product_ids))]
    return rows


def evidence_operational_snapshot(session: Session) -> dict[str, Any]:
    counts = dict(
        session.execute(
            select(ShoppingEvidenceVersion.status, func.count()).group_by(
                ShoppingEvidenceVersion.status
            )
        ).all()
    )
    task_counts = dict(
        session.execute(
            select(ShoppingIngestionTask.status, func.count()).group_by(
                ShoppingIngestionTask.status
            )
        ).all()
    )
    return {
        "evidence": {str(key): int(value) for key, value in counts.items()},
        "tasks": {str(key): int(value) for key, value in task_counts.items()},
        "bounded": True,
    }


__all__ = [
    "claim_ingestion_tasks",
    "create_ingestion_task",
    "evidence_operational_snapshot",
    "get_ingestion_task",
    "list_current_evidence",
    "mark_node_completed",
    "mark_node_running",
    "mark_task_failed",
    "publish_evidence_version",
    "revoke_evidence",
]
