import json

from evaluation.run_planner_eval import main
from evaluation.shopmind_planner_eval import (
    PLANNER_EVAL_CASES,
    evaluate_planner_policy,
    format_planner_eval_summary,
    run_planner_eval_case,
)


def test_planner_eval_cases_cover_required_policy_trajectories() -> None:
    scenarios = {case["scenario"] for case in PLANNER_EVAL_CASES}

    assert scenarios == {
        "accepted",
        "route_injection",
        "dependency_injection",
        "parallelism_escalation",
        "execution_mode_escalation",
        "run_identity_spoof",
        "malformed_contract",
        "provider_error",
    }
    assert any(not case["routes"] for case in PLANNER_EVAL_CASES)
    assert any(case.get("parallel_enabled") for case in PLANNER_EVAL_CASES)


def test_planner_policy_eval_passes_all_fixed_cases() -> None:
    summary = evaluate_planner_policy()

    assert summary["schema_version"] == "shopmind.planner-policy-eval.v1"
    assert summary["passed_cases"] == summary["total_cases"] == 10
    assert summary["passed_checks"] == summary["total_checks"] == 70
    assert summary["pass_rate"] == 1.0
    assert summary["check_pass_rate"] == 1.0
    assert summary["failures"] == []


def test_write_guard_case_skips_provider_and_keeps_empty_canonical_plan() -> None:
    case = next(
        case for case in PLANNER_EVAL_CASES if case["name"] == "write_guard_skips_provider"
    )

    result = run_planner_eval_case(case)

    assert result["passed"] is True
    assert result["provider_calls"] == 0
    assert result["planner_type"] == "deterministic_route_plan"


def test_planner_eval_failure_output_is_sanitized_and_readable() -> None:
    broken_case = {
        **PLANNER_EVAL_CASES[0],
        "name": "expected_wrong_type",
        "expected_planner_type": "provider_fallback",
    }

    summary = evaluate_planner_policy(cases=(broken_case,))
    output = format_planner_eval_summary(summary)

    assert summary["passed_cases"] == 0
    assert summary["failures"][0]["failures"] == ["planner_type"]
    assert "expected_wrong_type" in output
    assert "private planner provider detail" not in output


def test_planner_eval_cli_supports_text_json_and_artifact(capsys, tmp_path) -> None:
    assert main([]) == 0
    text_output = capsys.readouterr().out
    assert "ShopMind V5 planner policy eval" in text_output
    assert "failures: none" in text_output

    assert main(["--json"]) == 0
    json_output = json.loads(capsys.readouterr().out)
    assert json_output["passed_cases"] == 10
    assert json_output["failures"] == []

    artifact_path = tmp_path / "nested" / "planner-summary.json"
    assert main(["--output-json", str(artifact_path)]) == 0
    artifact_output = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert artifact_output["passed_checks"] == 70
    assert artifact_output["failures"] == []
    assert not artifact_path.with_suffix(".json.tmp").exists()


def test_planner_eval_cli_writes_failure_artifact_before_nonzero_exit(
    capsys,
    monkeypatch,
    tmp_path,
) -> None:
    broken_case = {
        **PLANNER_EVAL_CASES[0],
        "name": "ci_policy_regression",
        "expected_planner_type": "provider_fallback",
    }
    failed_summary = evaluate_planner_policy(cases=(broken_case,))
    monkeypatch.setattr(
        "evaluation.run_planner_eval.evaluate_planner_policy",
        lambda: failed_summary,
    )
    artifact_path = tmp_path / "failed-summary.json"

    assert main(["--output-json", str(artifact_path)]) == 1
    artifact_output = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert artifact_output["passed_cases"] == 0
    assert artifact_output["failures"][0]["name"] == "ci_policy_regression"
    assert "ci_policy_regression" in capsys.readouterr().out
