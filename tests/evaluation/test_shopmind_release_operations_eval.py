import json

from evaluation.run_release_operations_eval import main
from evaluation.shopmind_release_operations_eval import (
    RELEASE_OPERATIONS_SCENARIOS,
    evaluate_release_operations,
)


def test_release_operations_gate_covers_closed_operational_trajectories() -> None:
    summary = evaluate_release_operations()

    assert summary["schema_version"] == (
        "shopmind.release-operations-eval.v1"
    )
    assert summary["total_cases"] == summary["passed_cases"] == 7
    assert summary["checks_passed"] == summary["total_checks"] == 42
    assert summary["failures"] == []
    assert tuple(case["name"] for case in summary["cases"]) == (
        RELEASE_OPERATIONS_SCENARIOS
    )

    outcomes = {
        case["name"]: case["outcome"] for case in summary["cases"]
    }
    assert outcomes["deployment_warmup"]["status"] == "hold"
    assert outcomes["rollback_unverified"]["recommended_action"] == (
        "block_rollback"
    )
    assert outcomes["incident_escalation"]["status"] == (
        "action_required"
    )
    serialized = json.dumps(summary, sort_keys=True)
    for forbidden in (
        "user_id",
        "request_id",
        "database_url",
        "redis_url",
        "private-host",
        "exception",
    ):
        assert forbidden not in serialized


def test_release_operations_runner_writes_json_artifact(tmp_path) -> None:
    output = tmp_path / "release-operations.json"

    assert main(["--output-json", str(output)]) == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["passed_cases"] == payload["total_cases"] == 7
