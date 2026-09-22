import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.operations import ShoppingTaskRollbackEvidence, evaluate_shopping_task_rollback
from evaluation.run_shopping_task_rollback_eval import run_cases


def test_shopping_task_rollback_gate_covers_required_boundaries() -> None:
    report = run_cases()
    assert report["passed"] == report["total"] == 6


def test_rollback_input_is_closed_and_report_is_value_free() -> None:
    evidence = ShoppingTaskRollbackEvidence(
        tasks_enabled=False,
        worker_state="drained",
        active_leases=0,
        confirmed_facts_preserved=True,
        migration_status="compatible",
        revoked_evidence_hidden=True,
    )
    report = evaluate_shopping_task_rollback(evidence)
    assert report.passed is True
    assert report.failures == ()
    payload = json.loads(report.model_dump_json())
    assert set(payload) == {"schema_version", "status", "passed", "checks", "failures"}
    with pytest.raises(ValidationError):
        ShoppingTaskRollbackEvidence.model_validate(
            {**evidence.model_dump(mode="json"), "database_url": "private"}
        )


def test_ci_runs_and_uploads_shopping_task_rollback_gate() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "Gate shopping task rollback checks" in workflow
    assert (
        "python evaluation/run_shopping_task_rollback_eval.py --output-json "
        "artifacts/shopping-task-rollback/summary.json"
    ) in workflow
    assert "name: shopping-task-rollback" in workflow
