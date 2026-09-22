"""Admin-only, payload-free shopping AI operations views."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app.ai_platform.contracts import EvidenceType
from app.ai_platform.admin import AdminAuthorizer
from app.ai_platform.model_registry import default_model_registry
from app.ai_platform.health import aggregate_ai_status
from app.ai_platform.operations import project_trace, record_admin_operation
from app.core.settings import get_settings
from app.db.session import SessionLocal
from app.repositories.shopping_evidence import (
    evidence_operational_snapshot,
    list_current_evidence,
    revoke_evidence,
)
from app.repositories.ai_extensions import publish_extension
from app.ai_platform.models import AIExtensionDefinition
from app.ai_platform.models import ShoppingEvidenceVersion
from sqlalchemy import select


router = APIRouter(prefix="/admin/ai", tags=["admin-ai"])


class AdminVersionRequest(BaseModel):
    expected_version: int = Field(ge=1)


class TraceProjectionRequest(BaseModel):
    events: list[dict[str, Any]] = Field(default_factory=list, max_length=100)


def _require_admin(request: Request) -> None:
    settings = getattr(request.app.state, "runtime_settings", None) or get_settings()
    if (
        not settings.shopmind_ai_platform_enabled
        or not settings.shopmind_ai_operations_enabled
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    authorizer = getattr(request.app.state, "admin_authorizer", AdminAuthorizer())
    if not callable(authorizer) or not bool(authorizer(request)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required"
        )


def _evidence_row(row) -> dict[str, Any]:
    return {
        "id": row.id,
        "evidence_key": row.evidence_key,
        "evidence_type": row.evidence_type,
        "source_name": row.source_name,
        "product_ids": list(row.product_ids or []),
        "sku_codes": list(row.sku_codes or []),
        "category_code": row.category_code,
        "policy_type": row.policy_type,
        "region": row.region,
        "channel": row.channel,
        "version": row.version,
        "status": row.status,
        "valid_from": row.valid_from.isoformat() if row.valid_from else None,
        "valid_until": row.valid_until.isoformat() if row.valid_until else None,
        "published_at": row.published_at.isoformat() if row.published_at else None,
    }


@router.get("/health")
async def ai_operations_health(request: Request) -> dict[str, Any]:
    _require_admin(request)
    resolved_settings = (
        getattr(request.app.state, "runtime_settings", None) or get_settings()
    )

    def read() -> dict[str, Any]:
        session = SessionLocal()
        try:
            snapshot = evidence_operational_snapshot(session)
        finally:
            session.close()
        model_health = default_model_registry(resolved_settings).gateway().health()
        return {
            "schema_version": "shopmind.ai-operations-health.v1",
            "status": aggregate_ai_status(
                enabled=resolved_settings.shopmind_ai_platform_enabled,
                model_health=model_health,
            ).value,
            "evidence": snapshot,
            "models": [item.model_dump(mode="json") for item in model_health],
            "rocketmq": "independent_outbox_publisher",
        }

    return await run_in_threadpool(read)


@router.get("/evidence")
async def list_evidence(
    request: Request,
    evidence_type: str | None = Query(default=None),
    category_code: str | None = Query(default=None, max_length=64),
    product_id: str | None = Query(default=None, max_length=64),
    policy_type: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=50, ge=1, le=100),
) -> dict[str, Any]:
    _require_admin(request)
    if evidence_type is not None and evidence_type not in {
        item.value for item in EvidenceType
    }:
        raise HTTPException(status_code=400, detail="Unsupported evidence type")

    def read() -> dict[str, Any]:
        session = SessionLocal()
        try:
            rows = list_current_evidence(
                session,
                evidence_type=evidence_type,
                category_code=category_code,
                product_ids=[product_id] if product_id else None,
                policy_type=policy_type,
                limit=limit,
            )
            return {
                "items": [_evidence_row(row) for row in rows],
                "limit": limit,
                "bounded": True,
            }
        finally:
            session.close()

    return await run_in_threadpool(read)


@router.get("/evidence/coverage")
async def evidence_coverage(
    request: Request, category_code: str | None = Query(default=None, max_length=64)
) -> dict[str, Any]:
    _require_admin(request)

    def read() -> dict[str, Any]:
        session = SessionLocal()
        try:
            rows = list_current_evidence(
                session, category_code=category_code, limit=100
            )
            all_versions = session.scalars(
                select(ShoppingEvidenceVersion)
                .order_by(ShoppingEvidenceVersion.id.desc())
                .limit(100)
            ).all()
            by_type: dict[str, int] = {}
            product_ids: set[str] = set()
            policy_types: set[str] = set()
            for row in rows:
                by_type[row.evidence_type] = by_type.get(row.evidence_type, 0) + 1
                product_ids.update(str(value) for value in (row.product_ids or []))
                if row.policy_type:
                    policy_types.add(row.policy_type)
            expired_versions = sum(
                1
                for row in all_versions
                if row.status == "published"
                and row.valid_until is not None
                and row.valid_until <= datetime.now(timezone.utc)
            )
            invalid_references = sum(
                1
                for row in all_versions
                if row.status == "failed"
                or (row.metadata_json or {}).get("validation_error")
            )
            return {
                "category_code": category_code,
                "active_evidence_versions": len(rows),
                "by_evidence_type": by_type,
                "covered_product_ids": len(product_ids),
                "active_policy_types": sorted(policy_types),
                "expired_versions": expired_versions,
                "invalid_catalog_references": invalid_references,
                "missing_evidence": 0,
                "corpus_overview_drift": False,
                "bounded": True,
            }
        finally:
            session.close()

    return await run_in_threadpool(read)


@router.post("/extensions/{definition_id}/publish")
async def activate_extension(
    definition_id: int,
    body: AdminVersionRequest,
    request: Request,
) -> dict[str, Any]:
    _require_admin(request)
    resolved_settings = (
        getattr(request.app.state, "runtime_settings", None) or get_settings()
    )

    def write() -> dict[str, Any]:
        session = SessionLocal()
        try:
            row = session.get(AIExtensionDefinition, definition_id)
            if row is None:
                raise HTTPException(status_code=404, detail="Extension not found")
            if row.version != body.expected_version:
                raise HTTPException(
                    status_code=409, detail="Extension version is stale"
                )
            published = publish_extension(session, definition_id)
            session.commit()
            record_admin_operation(
                operation="extension_published",
                resource_type="extension",
                resource_key=f"{published.extension_type}:{published.extension_key}",
                version=published.version,
                audit_enabled=bool(
                    getattr(
                        resolved_settings, "shopmind_governance_audit_enabled", False
                    )
                ),
                session_factory=SessionLocal,
            )
            return {
                "status": "published",
                "version": published.version,
                "bounded": True,
            }
        except HTTPException:
            session.rollback()
            raise
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    return await run_in_threadpool(write)


@router.post("/evidence/revoke")
async def revoke_evidence_version(
    body: AdminVersionRequest,
    request: Request,
    evidence_key: str = Query(min_length=1, max_length=160),
) -> dict[str, Any]:
    _require_admin(request)
    resolved_settings = (
        getattr(request.app.state, "runtime_settings", None) or get_settings()
    )

    def write() -> dict[str, Any]:
        session = SessionLocal()
        try:
            rows = list_current_evidence(session, limit=100)
            current = next(
                (row for row in rows if row.evidence_key == evidence_key), None
            )
            if current is None:
                raise HTTPException(status_code=404, detail="Evidence not found")
            if current.version != body.expected_version:
                raise HTTPException(status_code=409, detail="Evidence version is stale")
            changed = revoke_evidence(session, evidence_key)
            session.commit()
            record_admin_operation(
                operation="evidence_revoked",
                resource_type="evidence",
                resource_key=evidence_key,
                version=body.expected_version,
                audit_enabled=bool(
                    getattr(
                        resolved_settings, "shopmind_governance_audit_enabled", False
                    )
                ),
                session_factory=SessionLocal,
            )
            return {
                "status": "revoked" if changed else "not_found",
                "version": body.expected_version,
                "bounded": True,
            }
        except HTTPException:
            session.rollback()
            raise
        finally:
            session.close()

    return await run_in_threadpool(write)


@router.post("/trace/project")
async def project_trace_endpoint(
    body: TraceProjectionRequest, request: Request
) -> dict[str, Any]:
    _require_admin(request)
    return {"events": project_trace(body.events), "bounded": True}
