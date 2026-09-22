"""Deterministic rollback gate for the optional shopping task workbench."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.operations import ShoppingTaskRollbackEvidence, evaluate_shopping_task_rollback


def _evidence(**overrides) -> ShoppingTaskRollbackEvidence:
    values = {
        "tasks_enabled": False,
        "worker_state": "drained",
        "active_leases": 0,
        "confirmed_facts_preserved": True,
        "migration_status": "compatible",
        "revoked_evidence_hidden": True,
    }
    values.update(overrides)
    return ShoppingTaskRollbackEvidence(**values)


def run_cases() -> dict[str, object]:
    cases = {
        "ready": evaluate_shopping_task_rollback(_evidence()),
        "admission_enabled": evaluate_shopping_task_rollback(
            _evidence(tasks_enabled=True)
        ),
        "active_worker_lease": evaluate_shopping_task_rollback(
            _evidence(worker_state="active", active_leases=1)
        ),
        "confirmed_fact_missing": evaluate_shopping_task_rollback(
            _evidence(confirmed_facts_preserved=False)
        ),
        "revoked_evidence_visible": evaluate_shopping_task_rollback(
            _evidence(revoked_evidence_hidden=False)
        ),
        "migration_unverified": evaluate_shopping_task_rollback(
            _evidence(migration_status="unverified")
        ),
    }
    checks = {
        "ready": cases["ready"].passed,
        "admission_enabled": cases["admission_enabled"].failures
        == ("admission_disabled",),
        "active_worker_lease": set(cases["active_worker_lease"].failures)
        == {"worker_stopped", "leases_released"},
        "confirmed_fact_missing": cases["confirmed_fact_missing"].failures
        == ("confirmed_facts_preserved",),
        "revoked_evidence_visible": cases["revoked_evidence_visible"].failures
        == ("revoked_evidence_hidden",),
        "migration_unverified": cases["migration_unverified"].failures
        == ("migration_compatible",),
    }
    return {
        "schema_version": "shopmind.shopping-task-rollback-eval.v1",
        "passed": sum(checks.values()),
        "total": len(checks),
        "checks": checks,
        "cases": {
            name: report.model_dump(mode="json") for name, report in cases.items()
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run shopping task rollback gate.")
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args(argv)
    report = run_cases()
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    print(payload)
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(payload, encoding="utf-8")
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
