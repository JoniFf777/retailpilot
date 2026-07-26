import json

import pytest

from evaluation.run_governance_lifecycle_eval import main
from evaluation.shopmind_governance_lifecycle_eval import (
    GOVERNANCE_LIFECYCLE_SCENARIOS,
    evaluate_governance_lifecycle,
    replay_governance_lifecycle_case,
)


def test_governance_lifecycle_cases_cover_slice4_boundaries() -> None:
    assert set(GOVERNANCE_LIFECYCLE_SCENARIOS) == {
        "signed_identity_replay",
        "owner_memory_lifecycle",
        "owner_full_deletion",
        "audit_monitor_recovery",
        "audit_persistence_idempotency",
    }


def test_governance_lifecycle_gate_passes_all_cases() -> None:
    summary = evaluate_governance_lifecycle()

    assert summary["schema_version"] == "shopmind.governance-lifecycle-eval.v1"
    assert summary["passed_cases"] == summary["total_cases"] == 5
    assert summary["passed_checks"] == summary["total_checks"] == 42
    assert summary["failures"] == []


def test_governance_lifecycle_replay_is_deterministic_and_private_free() -> None:
    first = evaluate_governance_lifecycle()
    second = evaluate_governance_lifecycle()
    serialized = json.dumps(first, sort_keys=True)

    assert first == second
    assert "governance-eval-signing-secret" not in serialized
    assert "private-signed-governance-owner" not in serialized
    assert "private owner deletion content" not in serialized
    assert "private action preview" not in serialized


def test_governance_lifecycle_rejects_unknown_case() -> None:
    with pytest.raises(ValueError, match="Unknown governance lifecycle"):
        replay_governance_lifecycle_case("dynamic_unregistered_case")


def test_governance_lifecycle_cli_writes_artifact(capsys, tmp_path) -> None:
    output = tmp_path / "governance-lifecycle.json"

    assert main(["--output-json", str(output)]) == 0
    assert "failures: none" in capsys.readouterr().out
    artifact = json.loads(output.read_text(encoding="utf-8"))
    assert artifact["passed_cases"] == 5
    assert artifact["passed_checks"] == 42
