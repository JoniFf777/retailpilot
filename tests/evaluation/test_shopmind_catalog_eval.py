import copy
import json
from functools import lru_cache
from pathlib import Path

import pytest
from pydantic import ValidationError

from evaluation.run_catalog_eval import main
from evaluation.shopmind_catalog_eval import (
    REGRESSION_METRIC_DIRECTIONS,
    SUITE_RUNNERS,
    AcceptedBaseline,
    CatalogError,
    EvaluationCatalog,
    REQUIRED_CATEGORIES,
    compare_candidate_to_baseline,
    evaluate_catalog_regression,
    load_baseline,
    load_catalog,
)


@lru_cache(maxsize=1)
def _passing_summary() -> dict:
    return evaluate_catalog_regression()


def test_default_catalog_covers_required_v6_dimensions() -> None:
    catalog = load_catalog()

    assert catalog.schema_version == "shopmind.evaluation-catalog.v1"
    assert catalog.catalog_id == "shopmind-v6-slice4"
    assert catalog.required_categories == REQUIRED_CATEGORIES
    assert len(catalog.suites) == 8
    assert {suite.runner for suite in catalog.suites} == set(SUITE_RUNNERS)
    assert all(suite.required for suite in catalog.suites)
    assert all(not Path(suite.artifact_path).is_absolute() for suite in catalog.suites)


def test_accepted_baseline_is_closed_and_aligned_with_catalog() -> None:
    catalog = load_catalog()
    baseline = load_baseline()

    assert baseline.catalog_id == catalog.catalog_id
    assert baseline.catalog_schema_version == catalog.schema_version
    assert set(baseline.suites) == {suite.suite_id for suite in catalog.suites}
    assert set(baseline.metrics) == set(REGRESSION_METRIC_DIRECTIONS)
    assert set(baseline.thresholds) == set(REGRESSION_METRIC_DIRECTIONS)
    assert all(threshold.allowed_delta == 0 for threshold in baseline.thresholds.values())


def test_catalog_gate_passes_accepted_deterministic_baseline() -> None:
    summary = copy.deepcopy(_passing_summary())

    assert summary["schema_version"] == "shopmind.evaluation-catalog-run.v1"
    assert summary["passed"] is True
    assert summary["suite_failures"] == []
    assert summary["candidate"]["passed_suites"] == 8
    assert summary["candidate"]["total_suites"] == 8
    assert summary["candidate"]["passed_cases"] == 61
    assert summary["candidate"]["total_cases"] == 61
    assert summary["candidate"]["passed_checks"] == 488
    assert summary["candidate"]["total_checks"] == 488
    assert summary["comparison"]["passed_checks"] == 48
    assert summary["comparison"]["total_checks"] == 48
    assert summary["comparison"]["failures"] == []


def test_catalog_rejects_missing_required_category_and_unknown_runner() -> None:
    raw_catalog = load_catalog().model_dump(mode="json")
    raw_catalog["required_categories"].remove("cost")

    with pytest.raises(ValidationError):
        EvaluationCatalog.model_validate(raw_catalog)

    raw_catalog = load_catalog().model_dump(mode="json")
    for suite in raw_catalog["suites"]:
        if "cost" in suite["categories"]:
            suite["categories"].remove("cost")

    with pytest.raises(ValidationError):
        EvaluationCatalog.model_validate(raw_catalog)

    raw_catalog = load_catalog().model_dump(mode="json")
    raw_catalog["suites"][0]["runner"] = "module.dynamic_callable"

    with pytest.raises(ValidationError):
        EvaluationCatalog.model_validate(raw_catalog)


def test_baseline_rejects_incomplete_metrics_and_weakened_direction() -> None:
    raw_baseline = load_baseline().model_dump(mode="json")
    del raw_baseline["metrics"]["cost_regression_count"]

    with pytest.raises(ValidationError):
        AcceptedBaseline.model_validate(raw_baseline)

    raw_baseline = load_baseline().model_dump(mode="json")
    raw_baseline["thresholds"]["quality_score"]["direction"] = "max"

    with pytest.raises(ValidationError):
        AcceptedBaseline.model_validate(raw_baseline)


@pytest.mark.parametrize(
    ("mutation", "expected_check"),
    (
        ("quality", "metric:quality_score"),
        ("safety", "metric:safety_score"),
        ("latency", "metric:latency_regression_count"),
        ("token", "metric:token_regression_count"),
        ("cost", "metric:cost_regression_count"),
        ("suite_checks", "suite:plan_trajectory:passed_checks"),
    ),
)
def test_regression_comparison_fails_closed(
    mutation: str,
    expected_check: str,
) -> None:
    catalog = load_catalog()
    baseline = load_baseline()
    candidate = copy.deepcopy(_passing_summary()["candidate"])
    if mutation == "quality":
        candidate["metrics"]["quality_score"] = 0.99
    elif mutation == "safety":
        candidate["metrics"]["safety_score"] = 0.99
    elif mutation in {"latency", "token", "cost"}:
        candidate["metrics"][f"{mutation}_regression_count"] = 1.0
    else:
        candidate["suites"]["plan_trajectory"]["passed_checks"] = 194

    comparison = compare_candidate_to_baseline(catalog, candidate, baseline)

    assert comparison["passed"] is False
    assert expected_check in {
        failure["check_id"] for failure in comparison["failures"]
    }


def test_suite_execution_errors_are_sanitized(monkeypatch) -> None:
    private_detail = "private runner backend detail"

    def fail_runner() -> dict:
        raise RuntimeError(private_detail)

    monkeypatch.setitem(SUITE_RUNNERS, "deterministic_router", fail_runner)

    with pytest.raises(CatalogError) as exc_info:
        evaluate_catalog_regression()

    assert "execution failed" in str(exc_info.value)
    assert private_detail not in str(exc_info.value)


def test_catalog_cli_emits_pass_and_safe_failure_artifacts(
    capsys,
    monkeypatch,
) -> None:
    written: list[tuple[dict, Path]] = []

    def capture_artifact(summary: dict, path: Path) -> None:
        written.append((copy.deepcopy(summary), path))

    monkeypatch.setattr(
        "evaluation.run_catalog_eval.write_json_artifact",
        capture_artifact,
    )
    passing = copy.deepcopy(_passing_summary())
    monkeypatch.setattr(
        "evaluation.run_catalog_eval.evaluate_catalog_regression",
        lambda **_kwargs: passing,
    )
    pass_artifact = Path("artifacts/pass/summary.json")

    assert main(["--output-json", str(pass_artifact)]) == 0
    assert "status: pass" in capsys.readouterr().out
    assert written[-1] == (passing, pass_artifact)

    def fail_catalog(**_kwargs) -> dict:
        raise CatalogError("private manifest parse detail")

    monkeypatch.setattr(
        "evaluation.run_catalog_eval.evaluate_catalog_regression",
        fail_catalog,
    )
    failure_artifact = Path("artifacts/fail/summary.json")

    assert main(["--output-json", str(failure_artifact)]) == 1
    output = capsys.readouterr().out
    failure, written_path = written[-1]
    assert written_path == failure_artifact
    assert failure["error"]["code"] == "evaluation.catalog_invalid"
    assert "private manifest parse detail" not in output
    assert "private manifest parse detail" not in json.dumps(failure)


def test_ci_workflow_gates_and_uploads_v6_catalog_regression() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    command = (
        "python evaluation/run_catalog_eval.py --artifacts-root . "
        "--reuse-existing --output-json "
        "artifacts/v6-evaluation-catalog/summary.json"
    )

    assert "Gate V6 evaluation catalog regression" in workflow
    assert command in workflow
    assert "Publish V6 evaluation catalog summary" in workflow
    assert "name: v6-evaluation-catalog-regression" in workflow
    assert "path: artifacts/v6-evaluation-catalog" in workflow
    assert "Gate V6 resilience and restart replay" in workflow
    assert "Gate V6 coordination backend equivalence" in workflow
    assert "name: v6-coordination-equivalence-eval" in workflow
    assert "Gate V6 governance lifecycle" in workflow
    assert "name: v6-governance-lifecycle-eval" in workflow
    assert "name: v6-resilience-replay-eval" in workflow
    assert workflow.index("Gate V6 resilience and restart replay") < workflow.index(
        "Gate V6 coordination backend equivalence"
    )
    assert workflow.index("Gate V6 coordination backend equivalence") < workflow.index(
        "Gate V6 governance lifecycle"
    )
    assert workflow.index("Gate V6 governance lifecycle") < workflow.index(
        "Gate V6 evaluation catalog regression"
    )
    assert workflow.index("Gate V6 evaluation catalog regression") < workflow.index(
        "Generate V3 event artifacts"
    )
