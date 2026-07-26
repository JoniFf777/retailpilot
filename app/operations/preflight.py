"""Closed, sanitized production-profile configuration preflight."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.settings import Settings


PRODUCTION_PREFLIGHT_SCHEMA_VERSION = "shopmind.production-preflight.v1"

ProductionPreflightCheckId = Literal[
    "identity.boundary",
    "coordination.topology",
    "governance.audit",
    "transport.rag",
    "retention.cleanup",
    "runtime.limits",
]


class ProductionPreflightCategory(StrEnum):
    IDENTITY = "identity"
    COORDINATION = "coordination"
    GOVERNANCE = "governance"
    TRANSPORT = "transport"
    RETENTION = "retention"
    RUNTIME = "runtime"


class ProductionPreflightCheckStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    NOT_APPLICABLE = "not_applicable"


class ProductionPreflightReason(StrEnum):
    DEVELOPMENT_PROFILE = "development_profile"
    SIGNED_IDENTITY = "signed_identity"
    TRUSTED_PROXY_IDENTITY = "trusted_proxy_identity"
    DEVELOPMENT_IDENTITY_FORBIDDEN = "development_identity_forbidden"
    TRUSTED_PROXY_UNVERIFIED = "trusted_proxy_unverified"
    SINGLE_REPLICA_LOCAL = "single_replica_local"
    REDIS_COORDINATION = "redis_coordination"
    LOCAL_COORDINATION_MULTI_REPLICA = "local_coordination_multi_replica"
    REDIS_URL_MISSING = "redis_url_missing"
    GOVERNANCE_AUDIT_ENABLED = "governance_audit_enabled"
    GOVERNANCE_AUDIT_DISABLED = "governance_audit_disabled"
    IN_PROCESS_TRANSPORT = "in_process_transport"
    HTTPS_TRANSPORT = "https_transport"
    HTTP_TRANSPORT_INVALID = "http_transport_invalid"
    RETENTION_CLEANUP_SCHEDULED = "retention_cleanup_scheduled"
    RETENTION_CLEANUP_UNSCHEDULED = "retention_cleanup_unscheduled"
    RUNTIME_LIMITS_BOUNDED = "runtime_limits_bounded"
    RUNTIME_LIMITS_UNBOUNDED = "runtime_limits_unbounded"


class ProductionPreflightCheck(BaseModel):
    """One closed check with no arbitrary detail or configuration value."""

    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=True)

    check_id: ProductionPreflightCheckId
    category: ProductionPreflightCategory
    status: ProductionPreflightCheckStatus
    reason: ProductionPreflightReason


class ProductionPreflightReport(BaseModel):
    """Sanitized aggregate safe for CLI artifacts and internal health output."""

    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=True)

    schema_version: Literal["shopmind.production-preflight.v1"] = (
        PRODUCTION_PREFLIGHT_SCHEMA_VERSION
    )
    profile: Literal["development", "production"]
    status: Literal["not_applicable", "ready", "blocked"]
    ready: bool
    total_checks: int = Field(ge=0)
    passed_checks: int = Field(ge=0)
    failed_checks: int = Field(ge=0)
    checks: tuple[ProductionPreflightCheck, ...]

    @model_validator(mode="after")
    def validate_aggregate(self) -> "ProductionPreflightReport":
        if self.total_checks != len(self.checks):
            raise ValueError("Production preflight check count is invalid.")
        passed = sum(check.status == "passed" for check in self.checks)
        failed = sum(check.status == "failed" for check in self.checks)
        if self.passed_checks != passed or self.failed_checks != failed:
            raise ValueError("Production preflight aggregate is invalid.")
        if self.profile == "development":
            if self.status != "not_applicable" or self.ready or failed:
                raise ValueError("Development preflight state is invalid.")
        elif self.ready != (self.status == "ready" and failed == 0):
            raise ValueError("Production preflight state is invalid.")
        return self


class ProductionPreflightError(RuntimeError):
    """Fail startup without carrying settings, URLs, secrets, or raw errors."""

    def __init__(self, report: ProductionPreflightReport) -> None:
        super().__init__("ShopMind production preflight failed.")
        self.report = report


def _check(
    check_id: ProductionPreflightCheckId,
    category: ProductionPreflightCategory,
    *,
    passed: bool,
    passed_reason: ProductionPreflightReason,
    failed_reason: ProductionPreflightReason,
) -> ProductionPreflightCheck:
    return ProductionPreflightCheck(
        check_id=check_id,
        category=category,
        status=(
            ProductionPreflightCheckStatus.PASSED
            if passed
            else ProductionPreflightCheckStatus.FAILED
        ),
        reason=passed_reason if passed else failed_reason,
    )


def _identity_check(settings: Settings) -> ProductionPreflightCheck:
    if settings.shopmind_identity_provider == "signed_header":
        return _check(
            "identity.boundary",
            ProductionPreflightCategory.IDENTITY,
            passed=True,
            passed_reason=ProductionPreflightReason.SIGNED_IDENTITY,
            failed_reason=(
                ProductionPreflightReason.DEVELOPMENT_IDENTITY_FORBIDDEN
            ),
        )
    if settings.shopmind_identity_provider == "trusted_header":
        return _check(
            "identity.boundary",
            ProductionPreflightCategory.IDENTITY,
            passed=settings.shopmind_trusted_proxy_authentication,
            passed_reason=ProductionPreflightReason.TRUSTED_PROXY_IDENTITY,
            failed_reason=ProductionPreflightReason.TRUSTED_PROXY_UNVERIFIED,
        )
    return _check(
        "identity.boundary",
        ProductionPreflightCategory.IDENTITY,
        passed=False,
        passed_reason=ProductionPreflightReason.SIGNED_IDENTITY,
        failed_reason=(
            ProductionPreflightReason.DEVELOPMENT_IDENTITY_FORBIDDEN
        ),
    )


def _coordination_check(settings: Settings) -> ProductionPreflightCheck:
    if settings.shopmind_coordination_backend == "redis":
        configured = (
            settings.shopmind_coordination_redis_url is not None
            and bool(
                settings.shopmind_coordination_redis_url
                .get_secret_value()
                .strip()
            )
        )
        return _check(
            "coordination.topology",
            ProductionPreflightCategory.COORDINATION,
            passed=configured,
            passed_reason=ProductionPreflightReason.REDIS_COORDINATION,
            failed_reason=ProductionPreflightReason.REDIS_URL_MISSING,
        )
    return _check(
        "coordination.topology",
        ProductionPreflightCategory.COORDINATION,
        passed=settings.shopmind_deployment_replicas == 1,
        passed_reason=ProductionPreflightReason.SINGLE_REPLICA_LOCAL,
        failed_reason=(
            ProductionPreflightReason.LOCAL_COORDINATION_MULTI_REPLICA
        ),
    )


def _governance_check(settings: Settings) -> ProductionPreflightCheck:
    return _check(
        "governance.audit",
        ProductionPreflightCategory.GOVERNANCE,
        passed=settings.shopmind_governance_audit_enabled,
        passed_reason=ProductionPreflightReason.GOVERNANCE_AUDIT_ENABLED,
        failed_reason=ProductionPreflightReason.GOVERNANCE_AUDIT_DISABLED,
    )


def _http_transport_is_valid(settings: Settings) -> bool:
    endpoint = settings.shopmind_rag_agent_http_endpoint
    if not endpoint:
        return False
    try:
        parsed = urlsplit(endpoint)
        hostname = (parsed.hostname or "").lower()
        allowed_hosts = {
            host.strip().lower()
            for host in settings.shopmind_rag_agent_http_allowed_hosts
        }
        return (
            parsed.scheme == "https"
            and bool(hostname)
            and hostname in allowed_hosts
            and parsed.username is None
            and parsed.password is None
            and not parsed.query
            and not parsed.fragment
        )
    except (TypeError, ValueError):
        return False


def _transport_check(settings: Settings) -> ProductionPreflightCheck:
    if settings.shopmind_rag_agent_transport == "in_process":
        return _check(
            "transport.rag",
            ProductionPreflightCategory.TRANSPORT,
            passed=True,
            passed_reason=ProductionPreflightReason.IN_PROCESS_TRANSPORT,
            failed_reason=ProductionPreflightReason.HTTP_TRANSPORT_INVALID,
        )
    return _check(
        "transport.rag",
        ProductionPreflightCategory.TRANSPORT,
        passed=_http_transport_is_valid(settings),
        passed_reason=ProductionPreflightReason.HTTPS_TRANSPORT,
        failed_reason=ProductionPreflightReason.HTTP_TRANSPORT_INVALID,
    )


def _retention_check(settings: Settings) -> ProductionPreflightCheck:
    return _check(
        "retention.cleanup",
        ProductionPreflightCategory.RETENTION,
        passed=settings.shopmind_runtime_cleanup_scheduled,
        passed_reason=(
            ProductionPreflightReason.RETENTION_CLEANUP_SCHEDULED
        ),
        failed_reason=(
            ProductionPreflightReason.RETENTION_CLEANUP_UNSCHEDULED
        ),
    )


def _runtime_check(settings: Settings) -> ProductionPreflightCheck:
    bounded = all(
        value is not None and value > 0
        for value in (
            settings.shopmind_runtime_max_duration_ms,
            settings.shopmind_runtime_max_steps,
            settings.shopmind_runtime_max_tool_calls,
            settings.shopmind_runtime_max_total_tokens,
            settings.shopmind_runtime_max_cost_usd,
        )
    )
    return _check(
        "runtime.limits",
        ProductionPreflightCategory.RUNTIME,
        passed=bounded,
        passed_reason=ProductionPreflightReason.RUNTIME_LIMITS_BOUNDED,
        failed_reason=ProductionPreflightReason.RUNTIME_LIMITS_UNBOUNDED,
    )


def evaluate_production_preflight(
    settings: Settings,
) -> ProductionPreflightReport:
    """Evaluate only settings relationships; never probe external services."""

    if settings.shopmind_deployment_profile == "development":
        checks = tuple(
            ProductionPreflightCheck(
                check_id=check_id,
                category=category,
                status=ProductionPreflightCheckStatus.NOT_APPLICABLE,
                reason=ProductionPreflightReason.DEVELOPMENT_PROFILE,
            )
            for check_id, category in (
                ("identity.boundary", ProductionPreflightCategory.IDENTITY),
                (
                    "coordination.topology",
                    ProductionPreflightCategory.COORDINATION,
                ),
                ("governance.audit", ProductionPreflightCategory.GOVERNANCE),
                ("transport.rag", ProductionPreflightCategory.TRANSPORT),
                ("retention.cleanup", ProductionPreflightCategory.RETENTION),
                ("runtime.limits", ProductionPreflightCategory.RUNTIME),
            )
        )
        return ProductionPreflightReport(
            profile="development",
            status="not_applicable",
            ready=False,
            total_checks=len(checks),
            passed_checks=0,
            failed_checks=0,
            checks=checks,
        )

    checks = (
        _identity_check(settings),
        _coordination_check(settings),
        _governance_check(settings),
        _transport_check(settings),
        _retention_check(settings),
        _runtime_check(settings),
    )
    failed_checks = sum(check.status == "failed" for check in checks)
    return ProductionPreflightReport(
        profile="production",
        status="ready" if not failed_checks else "blocked",
        ready=not failed_checks,
        total_checks=len(checks),
        passed_checks=len(checks) - failed_checks,
        failed_checks=failed_checks,
        checks=checks,
    )


def assert_production_preflight(
    settings: Settings,
) -> ProductionPreflightReport:
    """Fail creation only when an explicitly selected production profile blocks."""

    report = evaluate_production_preflight(settings)
    if settings.shopmind_deployment_profile == "production" and not report.ready:
        raise ProductionPreflightError(report)
    return report


__all__ = [
    "PRODUCTION_PREFLIGHT_SCHEMA_VERSION",
    "ProductionPreflightCategory",
    "ProductionPreflightCheck",
    "ProductionPreflightCheckStatus",
    "ProductionPreflightError",
    "ProductionPreflightReason",
    "ProductionPreflightReport",
    "assert_production_preflight",
    "evaluate_production_preflight",
]
