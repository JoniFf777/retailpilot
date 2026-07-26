import json
from contextlib import contextmanager
from pathlib import Path

from evaluation.run_plan_trajectory_eval import main
from evaluation.shopmind_plan_trajectory_eval import (
    PLAN_TRAJECTORY_CASES,
    evaluate_plan_trajectories,
    format_plan_trajectory_summary,
    replay_plan_trajectory_case,
)


def test_plan_trajectory_cases_cover_graph_runtime_risks() -> None:
    assert {case["scenario"] for case in PLAN_TRAJECTORY_CASES} == {
        "completed",
        "partial_failure",
        "shared_budget",
        "shared_step_budget",
        "pre_cancelled",
        "cooperative_cancelled",
        "expired_deadline",
        "expired_duration",
        "retry_success",
        "retry_exhausted",
        "retry_non_retriable",
        "retry_budget_blocked",
        "retry_cancelled",
    }


def test_plan_trajectory_replay_disables_external_tracing(monkeypatch) -> None:
    tracing_enabled: list[bool | None] = []

    @contextmanager
    def fake_tracing_context(*, enabled=None, **_kwargs):
        tracing_enabled.append(enabled)
        yield

    monkeypatch.setattr(
        "evaluation.shopmind_plan_trajectory_eval.tracing_context",
        fake_tracing_context,
    )

    replay_plan_trajectory_case(PLAN_TRAJECTORY_CASES[0])

    assert tracing_enabled == [False]


def test_plan_trajectory_replay_passes_all_fixed_cases() -> None:
    summary = evaluate_plan_trajectories()

    assert summary["schema_version"] == "shopmind.plan-trajectory-eval.v2"
    assert summary["passed_cases"] == summary["total_cases"] == 13
    assert summary["passed_checks"] == summary["total_checks"] == 195
    assert summary["failures"] == []


def test_shared_budget_replay_is_normalized_and_bounded() -> None:
    case = next(
        case for case in PLAN_TRAJECTORY_CASES
        if case["scenario"] == "shared_budget"
    )

    result = replay_plan_trajectory_case(case)
    replayed = replay_plan_trajectory_case(case)

    assert result["passed"] is True
    assert result["trajectory"] == replayed["trajectory"]
    assert result["trajectory"]["gateway_call_count"] == 2
    assert result["trajectory"]["budget_respected"] is True
    assert result["trajectory"]["step_status_counts"] == {
        "completed": 2,
        "failed": 1,
    }


def test_shared_step_budget_replay_rejects_before_third_tool_call() -> None:
    case = next(
        case for case in PLAN_TRAJECTORY_CASES
        if case["scenario"] == "shared_step_budget"
    )

    result = replay_plan_trajectory_case(case)

    assert result["passed"] is True
    assert result["trajectory"]["tool_call_count"] == 2
    assert result["trajectory"]["tool_record_count"] == 2
    assert result["trajectory"]["budget_respected"] is True


def test_expired_time_budget_replays_reject_before_tool_calls() -> None:
    for scenario, error_code in (
        ("expired_deadline", "plan.deadline_exceeded"),
        ("expired_duration", "plan.duration_budget_exceeded"),
    ):
        case = next(
            case for case in PLAN_TRAJECTORY_CASES
            if case["scenario"] == scenario
        )

        result = replay_plan_trajectory_case(case)

        assert result["passed"] is True
        assert result["trajectory"]["tool_call_count"] == 0
        assert result["trajectory"]["tool_record_count"] == 0
        assert result["trajectory"]["gateway_call_count"] == 0
        assert result["trajectory"]["error_counts"] == {error_code: 3}


def test_retry_fault_trajectories_have_stable_attempt_sequences() -> None:
    retry_cases = [
        case for case in PLAN_TRAJECTORY_CASES
        if case["scenario"].startswith("retry_")
    ]

    for case in retry_cases:
        result = replay_plan_trajectory_case(case)

        assert result["passed"] is True
        assert result["trajectory"]["attempt_event_contract"] is True
        assert result["trajectory"]["rag_attempt_sequence"] == (
            case["expected_attempt_sequence"]
        )
        assert result["trajectory"]["attempt_counts"]["rag_agent"] == (
            case["expected_attempt_count"]
        )


def test_retry_success_preserves_single_tool_execution_after_replay() -> None:
    case = next(
        case for case in PLAN_TRAJECTORY_CASES
        if case["scenario"] == "retry_success"
    )

    result = replay_plan_trajectory_case(case)

    assert result["passed"] is True
    assert result["trajectory"]["status"] == "completed"
    assert result["trajectory"]["tool_call_count"] == 1
    assert result["trajectory"]["gateway_call_count"] == 1


def test_retry_budget_and_cancellation_block_before_second_attempt() -> None:
    for scenario, terminal_event in (
        ("retry_budget_blocked", "plan.step.retry.budget_blocked"),
        ("retry_cancelled", "plan.step.retry.cancelled"),
    ):
        case = next(
            case for case in PLAN_TRAJECTORY_CASES
            if case["scenario"] == scenario
        )

        result = replay_plan_trajectory_case(case)

        assert result["passed"] is True
        assert result["trajectory"]["attempt_counts"]["rag_agent"] == 1
        assert result["trajectory"]["rag_attempt_sequence"][-1] == terminal_event
        assert result["trajectory"]["tool_call_count"] == 0


def test_plan_trajectory_failure_output_is_readable() -> None:
    broken_case = {
        **PLAN_TRAJECTORY_CASES[0],
        "name": "expected_wrong_status",
        "expected_status": "partial",
    }

    summary = evaluate_plan_trajectories(cases=(broken_case,))
    output = format_plan_trajectory_summary(summary)

    assert summary["passed_cases"] == 0
    assert summary["failures"][0]["failures"] == ["status"]
    assert "expected_wrong_status" in output
    assert "private trajectory backend detail" not in output


def test_plan_trajectory_cli_supports_text_json_and_artifact(capsys, tmp_path) -> None:
    assert main([]) == 0
    assert "failures: none" in capsys.readouterr().out

    assert main(["--json"]) == 0
    json_output = json.loads(capsys.readouterr().out)
    assert json_output["passed_cases"] == 13

    artifact_path = tmp_path / "trajectory" / "summary.json"
    assert main(["--output-json", str(artifact_path)]) == 0
    artifact_output = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert artifact_output["passed_checks"] == 195
    assert not artifact_path.with_suffix(".json.tmp").exists()


def test_plan_trajectory_cli_writes_failure_artifact_before_nonzero_exit(
    capsys,
    monkeypatch,
    tmp_path,
) -> None:
    broken_case = {
        **PLAN_TRAJECTORY_CASES[0],
        "name": "ci_trajectory_regression",
        "expected_status": "partial",
    }
    failed_summary = evaluate_plan_trajectories(cases=(broken_case,))
    monkeypatch.setattr(
        "evaluation.run_plan_trajectory_eval.evaluate_plan_trajectories",
        lambda: failed_summary,
    )
    artifact_path = tmp_path / "failed-trajectory.json"

    assert main(["--output-json", str(artifact_path)]) == 1
    artifact_output = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert artifact_output["failures"][0]["name"] == "ci_trajectory_regression"
    assert "ci_trajectory_regression" in capsys.readouterr().out


def test_ci_workflow_gates_and_uploads_plan_trajectory_replay() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    command = (
        "python evaluation/run_plan_trajectory_eval.py --output-json "
        "artifacts/v5-plan-trajectories/summary.json"
    )

    assert "Gate V5 plan trajectory replay" in workflow
    assert 'SHOPMIND_AGENT_TASK_MAX_ATTEMPTS: "1"' in workflow
    assert command in workflow
    assert "Publish V5 plan trajectory summary" in workflow
    assert 'cat artifacts/v5-plan-trajectories/summary.md >> "$GITHUB_STEP_SUMMARY"' in workflow
    assert "name: v5-plan-trajectory-eval" in workflow
    assert "path: artifacts/v5-plan-trajectories/summary.json" in workflow
    assert workflow.index("Gate V5 planner policy") < workflow.index(
        "Gate V5 plan trajectory replay"
    )
    assert workflow.index("Gate V5 plan trajectory replay") < workflow.index(
        "Generate V3 event artifacts"
    )
