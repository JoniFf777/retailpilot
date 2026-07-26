import json

from evaluation.run_adapter_equivalence_eval import main
from evaluation.shopmind_adapter_equivalence_eval import (
    ADAPTER_EQUIVALENCE_CASES,
    evaluate_adapter_equivalence,
    format_adapter_equivalence_summary,
    replay_adapter_equivalence_case,
)


def test_adapter_equivalence_cases_cover_transport_contract() -> None:
    assert {case["scenario"] for case in ADAPTER_EQUIVALENCE_CASES} == {
        "success_equivalence",
        "timeout",
        "unavailable",
        "malformed",
        "oversized",
    }


def test_adapter_equivalence_gate_passes_all_fixed_cases() -> None:
    summary = evaluate_adapter_equivalence()

    assert summary["schema_version"] == "shopmind.adapter-equivalence-eval.v1"
    assert summary["passed_cases"] == summary["total_cases"] == 5
    assert summary["passed_checks"] == summary["total_checks"] == 24
    assert summary["failures"] == []


def test_success_case_proves_local_http_result_equivalence() -> None:
    result = replay_adapter_equivalence_case(ADAPTER_EQUIVALENCE_CASES[0])

    assert result["passed"] is True
    assert result["outcome"] == {
        "kind": "result",
        "status": "completed",
        "same_contract": True,
    }


def test_adapter_equivalence_failure_output_is_safe_and_readable() -> None:
    broken = {
        **ADAPTER_EQUIVALENCE_CASES[1],
        "name": "wrong_timeout_contract",
        "expected_outcome": "agent.transport_unavailable",
    }

    summary = evaluate_adapter_equivalence(cases=(broken,))
    output = format_adapter_equivalence_summary(summary)

    assert summary["passed_cases"] == 0
    assert summary["failures"][0]["failures"] == ["expected_outcome"]
    assert "wrong_timeout_contract" in output
    assert "specialists.eval.internal" not in output


def test_adapter_equivalence_cli_writes_json_artifact(capsys, tmp_path) -> None:
    output_path = tmp_path / "adapter-equivalence.json"

    assert main(["--output-json", str(output_path)]) == 0
    assert "failures: none" in capsys.readouterr().out
    artifact = json.loads(output_path.read_text(encoding="utf-8"))
    assert artifact["passed_cases"] == 5
