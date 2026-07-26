import json

from evaluation.run_action_lifecycle_eval import main
from evaluation.shopmind_action_lifecycle_eval import (
    ACTION_LIFECYCLE_CASES,
    evaluate_action_lifecycle,
    replay_action_lifecycle_case,
)


def test_action_lifecycle_cases_cover_required_transitions() -> None:
    assert {case["scenario"] for case in ACTION_LIFECYCLE_CASES} == {
        "confirm", "cancel", "expired", "cross_user", "cross_thread",
        "duplicate", "malformed", "edited", "resumed", "replayed",
    }


def test_action_lifecycle_gate_passes_all_cases() -> None:
    summary = evaluate_action_lifecycle()
    assert summary["schema_version"] == "shopmind.action-lifecycle-eval.v2"
    assert summary["passed_cases"] == summary["total_cases"] == 10
    assert summary["passed_checks"] == summary["total_checks"] == 60
    assert summary["failures"] == []


def test_action_lifecycle_replay_is_deterministic() -> None:
    case = ACTION_LIFECYCLE_CASES[0]
    first = replay_action_lifecycle_case(case)
    second = replay_action_lifecycle_case(case)
    assert first["outcome"] == second["outcome"]


def test_action_lifecycle_cli_writes_artifact(capsys, tmp_path) -> None:
    output = tmp_path / "action-lifecycle.json"
    assert main(["--output-json", str(output)]) == 0
    assert "failures: none" in capsys.readouterr().out
    assert json.loads(output.read_text(encoding="utf-8"))["passed_cases"] == 10
