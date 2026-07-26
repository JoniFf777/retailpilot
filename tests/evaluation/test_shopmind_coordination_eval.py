import json
from pathlib import Path

from evaluation.run_coordination_eval import main
from evaluation.shopmind_coordination_eval import evaluate_coordination_equivalence


def test_coordination_equivalence_covers_closed_operations_and_safe_failure() -> None:
    summary = evaluate_coordination_equivalence()

    assert summary["schema_version"] == "shopmind.coordination-equivalence-eval.v1"
    assert summary["passed_cases"] == summary["total_cases"] == 5
    assert summary["passed_checks"] == summary["total_checks"] == 18
    assert summary["failures"] == []
    assert {case["case_id"] for case in summary["cases"]} == {
        "admission_lease",
        "fixed_window_rate_limit",
        "duplicate_claim",
        "bounded_cache",
        "transport_failure",
    }


def test_coordination_equivalence_cli_writes_json_artifact(tmp_path: Path) -> None:
    output = tmp_path / "coordination.json"

    assert main(["--output-json", str(output), "--json"]) == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["failures"] == []
    assert payload["passed_checks"] == 18
