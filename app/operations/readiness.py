"""Closed, sanitized live deployment-readiness probes."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.settings import Settings
from app.db.version import MIGRATION_HEAD
from app.runtime.coordination_factory import (
    build_runtime_coordination_backend,
)
from app.shopping_tasks.models import ShoppingTaskWorkerHeartbeat

from .cleanup_evidence import (
    RuntimeCleanupEvidence,
    RuntimeCleanupEvidenceError,
    load_runtime_cleanup_evidence,
)
from .preflight import (
    ProductionPreflightReport,
    evaluate_production_preflight,
)


DEPLOYMENT_READINESS_SCHEMA_VERSION = "shopmind.deployment-readiness.v1"
LEGACY_MIGRATION_HEAD = "0017_ai_extension_registry"

DeploymentReadinessCheckId = Literal[
    "configuration.preflight",
    "postgres.connectivity",
    "postgres.migration",
    "coordination.backend",
    "retention.cleanup",
    "ai.platform",
    "shopping_tasks.worker",
]


class DeploymentReadinessCategory(StrEnum):
    CONFIGURATION = "configuration"
    DATABASE = "database"
    COORDINATION = "coordination"
    RETENTION = "retention"
    AI_PLATFORM = "ai_platform"
    SHOPPING_TASKS = "shopping_tasks"


class DeploymentReadinessCheckStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    NOT_APPLICABLE = "not_applicable"


class DeploymentReadinessReason(StrEnum):
    DEVELOPMENT_PROFILE = "development_profile"
    CONFIGURATION_READY = "configuration_ready"
    CONFIGURATION_BLOCKED = "configuration_blocked"
    POSTGRES_REACHABLE = "postgres_reachable"
    POSTGRES_UNAVAILABLE = "postgres_unavailable"
    MIGRATION_CURRENT = "migration_current"
    MIGRATION_UNAVAILABLE = "migration_unavailable"
    MIGRATION_OUTDATED = "migration_outdated"
    LOCAL_COORDINATION_READY = "local_coordination_ready"
    REDIS_COORDINATION_READY = "redis_coordination_ready"
    COORDINATION_UNAVAILABLE = "coordination_unavailable"
    CLEANUP_NOT_REQUIRED = "cleanup_not_required"
    CLEANUP_UNSCHEDULED = "cleanup_unscheduled"
    CLEANUP_EVIDENCE_UNCONFIGURED = "cleanup_evidence_unconfigured"
    CLEANUP_EVIDENCE_MISSING = "cleanup_evidence_missing"
    CLEANUP_EVIDENCE_INVALID = "cleanup_evidence_invalid"
    CLEANUP_EVIDENCE_STALE = "cleanup_evidence_stale"
    CLEANUP_RECENT = "cleanup_recent"
    AI_PLATFORM_DISABLED = "ai_platform_disabled"
    AI_PLATFORM_READY = "ai_platform_ready"
    SHOPPING_TASKS_DISABLED = "shopping_tasks_disabled"
    SHOPPING_TASK_WORKER_READY = "shopping_task_worker_ready"
    SHOPPING_TASK_WORKER_MISSING = "shopping_task_worker_missing"
    SHOPPING_TASK_WORKER_STALE = "shopping_task_worker_stale"
    SHOPPING_TASK_WORKER_UNAVAILABLE = "shopping_task_worker_unavailable"


class DeploymentReadinessCheck(BaseModel):
    """One live check carrying only closed status and reason values."""

    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=True)

    check_id: DeploymentReadinessCheckId
    category: DeploymentReadinessCategory
    status: DeploymentReadinessCheckStatus
    reason: DeploymentReadinessReason


class DeploymentReadinessReport(BaseModel):
    """Aggregate safe for health responses and CI artifacts."""

    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=True)

    schema_version: Literal["shopmind.deployment-readiness.v1"] = (
        DEPLOYMENT_READINESS_SCHEMA_VERSION
    )
    profile: Literal["development", "offline-demo", "production"]
    status: Literal["ready", "blocked"]
    ready: bool
    total_checks: int = Field(ge=0)
    passed_checks: int = Field(ge=0)
    failed_checks: int = Field(ge=0)
    not_applicable_checks: int = Field(ge=0)
    checks: tuple[DeploymentReadinessCheck, ...]

    @model_validator(mode="after")
    def validate_aggregate(self) -> "DeploymentReadinessReport":
        if self.total_checks != len(self.checks):
            raise ValueError("Deployment readiness check count is invalid.")
        passed = sum(check.status == "passed" for check in self.checks)
        failed = sum(check.status == "failed" for check in self.checks)
        not_applicable = sum(check.status == "not_applicable" for check in self.checks)
        if (
            self.passed_checks != passed
            or self.failed_checks != failed
            or self.not_applicable_checks != not_applicable
        ):
            raise ValueError("Deployment readiness aggregate is invalid.")
        if self.ready != (self.status == "ready" and failed == 0):
            raise ValueError("Deployment readiness state is invalid.")
        return self


def _check(
    check_id: DeploymentReadinessCheckId,
    category: DeploymentReadinessCategory,
    status: DeploymentReadinessCheckStatus,
    reason: DeploymentReadinessReason,
) -> DeploymentReadinessCheck:
    return DeploymentReadinessCheck(
        check_id=check_id,
        category=category,
        status=status,
        reason=reason,
    )


def _configuration_check(
    settings: Settings,
    report: ProductionPreflightReport,
) -> DeploymentReadinessCheck:
    if settings.shopmind_deployment_profile in {"development", "offline-demo"}:
        return _check(
            "configuration.preflight",
            DeploymentReadinessCategory.CONFIGURATION,
            DeploymentReadinessCheckStatus.NOT_APPLICABLE,
            DeploymentReadinessReason.DEVELOPMENT_PROFILE,
        )
    return _check(
        "configuration.preflight",
        DeploymentReadinessCategory.CONFIGURATION,
        (
            DeploymentReadinessCheckStatus.PASSED
            if report.ready
            else DeploymentReadinessCheckStatus.FAILED
        ),
        (
            DeploymentReadinessReason.CONFIGURATION_READY
            if report.ready
            else DeploymentReadinessReason.CONFIGURATION_BLOCKED
        ),
    )


def _ai_platform_check(settings: Settings) -> DeploymentReadinessCheck:
    if not getattr(settings, "shopmind_ai_platform_enabled", False):
        return _check(
            "ai.platform",
            DeploymentReadinessCategory.AI_PLATFORM,
            DeploymentReadinessCheckStatus.NOT_APPLICABLE,
            DeploymentReadinessReason.AI_PLATFORM_DISABLED,
        )
    return _check(
        "ai.platform",
        DeploymentReadinessCategory.AI_PLATFORM,
        DeploymentReadinessCheckStatus.PASSED,
        DeploymentReadinessReason.AI_PLATFORM_READY,
    )


def _shopping_tasks_check(
    settings: Settings,
    *,
    session_factory: Callable[[], Session],
    now: datetime,
) -> DeploymentReadinessCheck:
    if not settings.shopmind_shopping_tasks_enabled:
        return _check(
            "shopping_tasks.worker",
            DeploymentReadinessCategory.SHOPPING_TASKS,
            DeploymentReadinessCheckStatus.NOT_APPLICABLE,
            DeploymentReadinessReason.SHOPPING_TASKS_DISABLED,
        )
    session: Session | None = None
    try:
        session = session_factory()
        last_seen = session.scalar(
            select(func.max(ShoppingTaskWorkerHeartbeat.last_seen_at))
        )
    except Exception:
        return _check(
            "shopping_tasks.worker",
            DeploymentReadinessCategory.SHOPPING_TASKS,
            DeploymentReadinessCheckStatus.FAILED,
            DeploymentReadinessReason.SHOPPING_TASK_WORKER_UNAVAILABLE,
        )
    finally:
        if session is not None:
            try:
                session.close()
            except Exception:
                pass
    if last_seen is None:
        return _check(
            "shopping_tasks.worker",
            DeploymentReadinessCategory.SHOPPING_TASKS,
            DeploymentReadinessCheckStatus.FAILED,
            DeploymentReadinessReason.SHOPPING_TASK_WORKER_MISSING,
        )
    normalized = (
        last_seen.astimezone(timezone.utc)
        if last_seen.tzinfo is not None and last_seen.utcoffset() is not None
        else last_seen.replace(tzinfo=timezone.utc)
    )
    recent = (now - normalized).total_seconds() <= (
        settings.shopmind_shopping_task_worker_max_age_seconds
    )
    return _check(
        "shopping_tasks.worker",
        DeploymentReadinessCategory.SHOPPING_TASKS,
        (
            DeploymentReadinessCheckStatus.PASSED
            if recent
            else DeploymentReadinessCheckStatus.FAILED
        ),
        (
            DeploymentReadinessReason.SHOPPING_TASK_WORKER_READY
            if recent
            else DeploymentReadinessReason.SHOPPING_TASK_WORKER_STALE
        ),
    )


def _postgres_checks(
    session_factory: Callable[[], Session],
    *,
    shopping_tasks_enabled: bool,
) -> tuple[DeploymentReadinessCheck, DeploymentReadinessCheck]:
    def close_session(session: Session | None) -> None:
        if session is None:
            return
        try:
            session.close()
        except Exception:
            pass

    session: Session | None = None
    try:
        session = session_factory()
        session.execute(text("select 1")).scalar_one()
    except Exception:
        close_session(session)
        return (
            _check(
                "postgres.connectivity",
                DeploymentReadinessCategory.DATABASE,
                DeploymentReadinessCheckStatus.FAILED,
                DeploymentReadinessReason.POSTGRES_UNAVAILABLE,
            ),
            _check(
                "postgres.migration",
                DeploymentReadinessCategory.DATABASE,
                DeploymentReadinessCheckStatus.FAILED,
                DeploymentReadinessReason.MIGRATION_UNAVAILABLE,
            ),
        )

    connectivity = _check(
        "postgres.connectivity",
        DeploymentReadinessCategory.DATABASE,
        DeploymentReadinessCheckStatus.PASSED,
        DeploymentReadinessReason.POSTGRES_REACHABLE,
    )
    try:
        migration = session.execute(
            text("select version_num from alembic_version")
        ).scalar_one()
    except Exception:
        migration_check = _check(
            "postgres.migration",
            DeploymentReadinessCategory.DATABASE,
            DeploymentReadinessCheckStatus.FAILED,
            DeploymentReadinessReason.MIGRATION_UNAVAILABLE,
        )
    else:
        accepted_heads = (
            {MIGRATION_HEAD}
            if shopping_tasks_enabled
            else {LEGACY_MIGRATION_HEAD, MIGRATION_HEAD}
        )
        current = migration in accepted_heads
        migration_check = _check(
            "postgres.migration",
            DeploymentReadinessCategory.DATABASE,
            (
                DeploymentReadinessCheckStatus.PASSED
                if current
                else DeploymentReadinessCheckStatus.FAILED
            ),
            (
                DeploymentReadinessReason.MIGRATION_CURRENT
                if current
                else DeploymentReadinessReason.MIGRATION_OUTDATED
            ),
        )
    finally:
        close_session(session)
    return connectivity, migration_check


def _default_coordination_probe(settings: Settings) -> None:
    backend = build_runtime_coordination_backend(settings)
    close = getattr(backend, "close", None)
    if callable(close):
        close()


def _coordination_check(
    settings: Settings,
    probe: Callable[[Settings], None],
) -> DeploymentReadinessCheck:
    try:
        probe(settings)
    except Exception:
        return _check(
            "coordination.backend",
            DeploymentReadinessCategory.COORDINATION,
            DeploymentReadinessCheckStatus.FAILED,
            DeploymentReadinessReason.COORDINATION_UNAVAILABLE,
        )
    return _check(
        "coordination.backend",
        DeploymentReadinessCategory.COORDINATION,
        DeploymentReadinessCheckStatus.PASSED,
        (
            DeploymentReadinessReason.REDIS_COORDINATION_READY
            if settings.shopmind_coordination_backend == "redis"
            else DeploymentReadinessReason.LOCAL_COORDINATION_READY
        ),
    )


def _retention_check(
    settings: Settings,
    *,
    now: datetime,
    loader: Callable[[str], RuntimeCleanupEvidence | None],
) -> DeploymentReadinessCheck:
    if settings.shopmind_deployment_profile in {"development", "offline-demo"}:
        return _check(
            "retention.cleanup",
            DeploymentReadinessCategory.RETENTION,
            DeploymentReadinessCheckStatus.NOT_APPLICABLE,
            DeploymentReadinessReason.CLEANUP_NOT_REQUIRED,
        )
    if not settings.shopmind_runtime_cleanup_scheduled:
        return _check(
            "retention.cleanup",
            DeploymentReadinessCategory.RETENTION,
            DeploymentReadinessCheckStatus.FAILED,
            DeploymentReadinessReason.CLEANUP_UNSCHEDULED,
        )
    path = settings.shopmind_runtime_cleanup_evidence_path
    if path is None:
        return _check(
            "retention.cleanup",
            DeploymentReadinessCategory.RETENTION,
            DeploymentReadinessCheckStatus.FAILED,
            DeploymentReadinessReason.CLEANUP_EVIDENCE_UNCONFIGURED,
        )
    evidence_invalid = False
    try:
        evidence = loader(path)
    except RuntimeCleanupEvidenceError:
        evidence = None
        evidence_invalid = True
    except Exception:
        evidence = None
        evidence_invalid = True
    if evidence_invalid:
        return _check(
            "retention.cleanup",
            DeploymentReadinessCategory.RETENTION,
            DeploymentReadinessCheckStatus.FAILED,
            DeploymentReadinessReason.CLEANUP_EVIDENCE_INVALID,
        )
    if evidence is None:
        return _check(
            "retention.cleanup",
            DeploymentReadinessCategory.RETENTION,
            DeploymentReadinessCheckStatus.FAILED,
            DeploymentReadinessReason.CLEANUP_EVIDENCE_MISSING,
        )
    normalized_now = (
        now.astimezone(timezone.utc)
        if now.tzinfo is not None and now.utcoffset() is not None
        else None
    )
    if normalized_now is None:
        raise ValueError("Readiness clock must return an aware datetime.")
    age_seconds = (
        normalized_now - evidence.completed_at.astimezone(timezone.utc)
    ).total_seconds()
    if age_seconds < 0:
        return _check(
            "retention.cleanup",
            DeploymentReadinessCategory.RETENTION,
            DeploymentReadinessCheckStatus.FAILED,
            DeploymentReadinessReason.CLEANUP_EVIDENCE_INVALID,
        )
    recent = age_seconds <= settings.shopmind_runtime_cleanup_evidence_max_age_seconds
    return _check(
        "retention.cleanup",
        DeploymentReadinessCategory.RETENTION,
        (
            DeploymentReadinessCheckStatus.PASSED
            if recent
            else DeploymentReadinessCheckStatus.FAILED
        ),
        (
            DeploymentReadinessReason.CLEANUP_RECENT
            if recent
            else DeploymentReadinessReason.CLEANUP_EVIDENCE_STALE
        ),
    )


def evaluate_deployment_readiness(
    settings: Settings,
    *,
    session_factory: Callable[[], Session] | None = None,
    coordination_probe: Callable[[Settings], None] | None = None,
    cleanup_evidence_loader: (
        Callable[[str], RuntimeCleanupEvidence | None] | None
    ) = None,
    clock: Callable[[], datetime] | None = None,
    preflight_report: ProductionPreflightReport | None = None,
) -> DeploymentReadinessReport:
    """Probe required live dependencies without returning arbitrary values."""

    if session_factory is None:
        from app.db.session import SessionLocal

        session_factory = SessionLocal
    resolved_preflight = preflight_report or evaluate_production_preflight(settings)
    postgres_checks = _postgres_checks(
        session_factory,
        shopping_tasks_enabled=settings.shopmind_shopping_tasks_enabled,
    )
    checks = (
        _configuration_check(settings, resolved_preflight),
        *postgres_checks,
        _coordination_check(
            settings,
            coordination_probe or _default_coordination_probe,
        ),
        _ai_platform_check(settings),
        _shopping_tasks_check(
            settings,
            session_factory=session_factory,
            now=(clock or (lambda: datetime.now(timezone.utc)))(),
        ),
        _retention_check(
            settings,
            now=(clock or (lambda: datetime.now(timezone.utc)))(),
            loader=cleanup_evidence_loader or load_runtime_cleanup_evidence,
        ),
    )
    failed = sum(check.status == "failed" for check in checks)
    passed = sum(check.status == "passed" for check in checks)
    not_applicable = sum(check.status == "not_applicable" for check in checks)
    return DeploymentReadinessReport(
        profile=settings.shopmind_deployment_profile,
        status="ready" if failed == 0 else "blocked",
        ready=failed == 0,
        total_checks=len(checks),
        passed_checks=passed,
        failed_checks=failed,
        not_applicable_checks=not_applicable,
        checks=checks,
    )


__all__ = [
    "DEPLOYMENT_READINESS_SCHEMA_VERSION",
    "DeploymentReadinessCategory",
    "DeploymentReadinessCheck",
    "DeploymentReadinessCheckStatus",
    "DeploymentReadinessReason",
    "DeploymentReadinessReport",
    "evaluate_deployment_readiness",
]
