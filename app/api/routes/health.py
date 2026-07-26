from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.governance import (
    GovernanceAuditEmissionMonitor,
    governance_audit_monitor,
)
from app.operations import (
    evaluate_deployment_readiness,
    evaluate_production_preflight,
)
from app.runtime import (
    ServiceHealthReport,
    evaluate_service_slo,
    runtime_service_monitor,
)


router = APIRouter()
GOVERNANCE_AUDIT_HEALTH_SCHEMA_VERSION = (
    "shopmind.governance-audit-health.v1"
)


@router.get("/health")
async def health_check() -> Dict[str, str]:
    return {"status": "ok"}


def get_governance_audit_health_report(
    monitor: GovernanceAuditEmissionMonitor | None = None,
    settings=None,
) -> dict[str, Any]:
    """Return process-local counters only; never probe or expose audit rows."""

    resolved_monitor = monitor or governance_audit_monitor
    resolved_settings = settings or get_settings()
    snapshot = resolved_monitor.snapshot()
    audit_enabled = bool(
        getattr(
            resolved_settings,
            "shopmind_governance_audit_enabled",
            False,
        )
    )
    if not audit_enabled:
        status_value = "disabled"
    elif snapshot.alert_active:
        status_value = "degraded"
    elif snapshot.consecutive_failures:
        status_value = "warning"
    else:
        status_value = "ok"
    return {
        "schema_version": GOVERNANCE_AUDIT_HEALTH_SCHEMA_VERSION,
        "status": status_value,
        "audit_enabled": audit_enabled,
        "monitor": snapshot.model_dump(mode="json"),
    }


@router.get("/health/governance-audit")
async def governance_audit_health_check() -> dict[str, Any]:
    return get_governance_audit_health_report()


def get_service_metrics_health_report(
    *,
    monitor=None,
    settings=None,
) -> dict[str, Any]:
    """Return bounded process metrics and closed SLO state only."""

    resolved_monitor = monitor or runtime_service_monitor
    resolved_settings = settings or get_settings()
    metrics = resolved_monitor.snapshot()
    slo = evaluate_service_slo(
        metrics,
        minimum_runs=resolved_settings.shopmind_service_slo_min_runs,
        success_rate_target=(
            resolved_settings.shopmind_service_slo_success_rate_target
        ),
        p95_latency_target_ms=(
            resolved_settings.shopmind_service_slo_p95_latency_ms
        ),
    )
    return ServiceHealthReport(
        status=slo.status,
        metrics=metrics,
        slo=slo,
    ).model_dump(mode="json")


@router.get("/health/service-metrics")
async def service_metrics_health_check(
    request: Request,
) -> dict[str, Any]:
    settings = getattr(request.app.state, "runtime_settings", None)
    return get_service_metrics_health_report(settings=settings)


def get_production_preflight_health_report(settings=None) -> dict[str, Any]:
    """Return only the closed static preflight; never expose configuration."""

    resolved_settings = settings or get_settings()
    return evaluate_production_preflight(resolved_settings).model_dump(
        mode="json"
    )


@router.get("/health/preflight")
async def production_preflight_health_check(
    request: Request,
) -> dict[str, Any]:
    report = getattr(request.app.state, "production_preflight", None)
    if report is not None:
        return report.model_dump(mode="json")
    return get_production_preflight_health_report()


def get_deployment_readiness_health_report(
    *,
    settings=None,
    preflight_report=None,
    session_factory=None,
) -> dict[str, Any]:
    """Return closed live dependency checks without values or raw errors."""

    resolved_settings = settings or get_settings()
    return evaluate_deployment_readiness(
        resolved_settings,
        session_factory=session_factory,
        preflight_report=preflight_report,
    ).model_dump(mode="json")


@router.get("/health/readiness")
async def deployment_readiness_health_check(
    request: Request,
) -> JSONResponse:
    settings = getattr(request.app.state, "runtime_settings", None)
    preflight = getattr(request.app.state, "production_preflight", None)
    report = await run_in_threadpool(
        lambda: get_deployment_readiness_health_report(
            settings=settings,
            preflight_report=preflight,
        )
    )
    return JSONResponse(
        status_code=200 if report["ready"] else 503,
        content=report,
    )


def get_postgres_health_report(session_factory=None) -> dict[str, Any]:
    """Run a read-only PostgreSQL health check."""
    if session_factory is None:
        from app.db.session import SessionLocal

        session_factory = SessionLocal

    session: Session = session_factory()
    try:
        database_name, database_user = session.execute(
            text("select current_database(), current_user")
        ).one()
        alembic_version = session.execute(
            text("select version_num from alembic_version")
        ).scalar_one()
        return {
            "status": "ok",
            "database": database_name,
            "user": database_user,
            "alembic_version": alembic_version,
        }
    finally:
        session.close()


@router.get("/health/postgres")
async def postgres_health_check() -> dict[str, Any]:
    try:
        return await run_in_threadpool(get_postgres_health_report)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "error",
                "message": "PostgreSQL health check failed",
                "reason": "postgres_unavailable",
            },
        ) from exc
