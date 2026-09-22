"""Closed rollback evidence for the optional shopping task workbench."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ShoppingTaskRollbackEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["shopmind.shopping-task-rollback-input.v1"] = (
        "shopmind.shopping-task-rollback-input.v1"
    )
    tasks_enabled: bool
    worker_state: Literal["drained", "cancelled", "active", "unknown"]
    active_leases: int = Field(ge=0)
    confirmed_facts_preserved: bool
    migration_status: Literal["compatible", "incompatible", "unverified"]
    revoked_evidence_hidden: bool


class ShoppingTaskRollbackReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["shopmind.shopping-task-rollback-check.v1"] = (
        "shopmind.shopping-task-rollback-check.v1"
    )
    status: Literal["ready", "blocked"]
    passed: bool
    checks: dict[str, bool]
    failures: tuple[str, ...]


def evaluate_shopping_task_rollback(
    evidence: ShoppingTaskRollbackEvidence,
) -> ShoppingTaskRollbackReport:
    checks = {
        "admission_disabled": evidence.tasks_enabled is False,
        "worker_stopped": evidence.worker_state in {"drained", "cancelled"},
        "leases_released": evidence.active_leases == 0,
        "confirmed_facts_preserved": evidence.confirmed_facts_preserved,
        "migration_compatible": evidence.migration_status == "compatible",
        "revoked_evidence_hidden": evidence.revoked_evidence_hidden,
    }
    failures = tuple(check_id for check_id, passed in checks.items() if not passed)
    return ShoppingTaskRollbackReport(
        status="ready" if not failures else "blocked",
        passed=not failures,
        checks=checks,
        failures=failures,
    )


__all__ = [
    "ShoppingTaskRollbackEvidence",
    "ShoppingTaskRollbackReport",
    "evaluate_shopping_task_rollback",
]
