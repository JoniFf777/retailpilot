import copy
import json
from functools import lru_cache

from evaluation.run_resilience_replay_eval import main
from evaluation.shopmind_resilience_replay_eval import (
    RESILIENCE_SCENARIOS,
    evaluate_resilience_replay,
)


@lru_cache(maxsize=1)
def _passing_summary() -> dict:
    return evaluate_resilience_replay()


def test_resilience_catalog_is_closed_and_covers_required_surfaces() -> None:
    assert [scenario.scenario_id for scenario in RESILIENCE_SCENARIOS] == [
        "provider_fallback",
        "tool_failure",
        "transport_retry_success",
        "transport_retry_cancelled",
        "idempotency_restart_replay",
        "action_restart_resume",
    ]
    assert {scenario.fault_surface for scenario in RESILIENCE_SCENARIOS} == {
        "provider", "tool", "transport", "control", "idempotency", "action"
    }


def test_resilience_restart_replay_gate_passes_and_sanitizes_faults() -> None:
    summary = copy.deepcopy(_passing_summary())

    assert summary["schema_version"] == "shopmind.resilience-replay-eval.v1"
    assert summary["passed_cases"] == summary["total_cases"] == 6
    assert summary["passed_checks"] == summary["total_checks"] == 72
    assert summary["failures"] == []
    assert "private-fault-detail" not in json.dumps(summary)


def test_resilience_cli_writes_the_closed_summary(monkeypatch, capsys) -> None:
    summary = copy.deepcopy(_passing_summary())
    written = []
    monkeypatch.setattr(
        "evaluation.run_resilience_replay_eval.evaluate_resilience_replay",
        lambda: summary,
    )
    monkeypatch.setattr(
        "evaluation.run_resilience_replay_eval.write_json_artifact",
        lambda payload, path: written.append((payload, path)),
    )

    assert main(["--output-json", "artifacts/resilience.json"]) == 0
    assert "cases: 6/6" in capsys.readouterr().out
    assert written[0][0] == summary
    assert str(written[0][1]) == "artifacts\\resilience.json"
