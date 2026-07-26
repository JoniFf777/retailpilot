"""Versioned V6 evaluation catalog and accepted-baseline comparison."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agents.shopmind_multi_agent.supervisor_router import (
    DeterministicSupervisorRouter,
)
from evaluation.json_artifacts import write_json_artifact
from evaluation.shopmind_action_lifecycle_eval import evaluate_action_lifecycle
from evaluation.shopmind_adapter_equivalence_eval import (
    evaluate_adapter_equivalence,
)
from evaluation.shopmind_coordination_eval import evaluate_coordination_equivalence
from evaluation.shopmind_governance_lifecycle_eval import (
    evaluate_governance_lifecycle,
)
from evaluation.shopmind_plan_trajectory_eval import evaluate_plan_trajectories
from evaluation.shopmind_planner_eval import evaluate_planner_policy
from evaluation.shopmind_resilience_replay_eval import evaluate_resilience_replay
from evaluation.shopmind_router_eval import evaluate_supervisor_router


DEFAULT_CATALOG_PATH = Path("evaluation/catalog/v6_evaluation_catalog.json")
DEFAULT_BASELINE_PATH = Path("evaluation/baselines/v6_slice4_accepted.json")


class CatalogError(ValueError):
    """Raised when catalog or baseline policy fails closed."""


class EvaluationCategory(StrEnum):
    PER_AGENT = "per_agent"
    ROUTER = "router"
    ANSWER = "answer"
    TRAJECTORY = "trajectory"
    MULTI_TURN = "multi_turn"
    MEMORY = "memory"
    SAFETY = "safety"
    LATENCY = "latency"
    TOKEN = "token"
    COST = "cost"
    PLANNER = "planner"
    ADAPTER = "adapter"
    ACTION = "action"
    IDENTITY = "identity"
    GOVERNANCE = "governance"
    PRIVACY = "privacy"


REQUIRED_CATEGORIES: tuple[EvaluationCategory, ...] = (
    EvaluationCategory.PER_AGENT,
    EvaluationCategory.ROUTER,
    EvaluationCategory.ANSWER,
    EvaluationCategory.TRAJECTORY,
    EvaluationCategory.MULTI_TURN,
    EvaluationCategory.MEMORY,
    EvaluationCategory.SAFETY,
    EvaluationCategory.LATENCY,
    EvaluationCategory.TOKEN,
    EvaluationCategory.COST,
)

RunnerName = Literal[
    "deterministic_router",
    "planner_policy",
    "plan_trajectory",
    "adapter_equivalence",
    "action_lifecycle",
    "resilience_replay",
    "coordination_equivalence",
    "governance_lifecycle",
]


class CatalogSuite(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    suite_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    runner: RunnerName
    artifact_schema: str = Field(min_length=1)
    artifact_path: str = Field(min_length=1)
    categories: tuple[EvaluationCategory, ...] = Field(min_length=1)
    required: bool = True

    @model_validator(mode="after")
    def validate_closed_fields(self) -> "CatalogSuite":
        if len(set(self.categories)) != len(self.categories):
            raise ValueError("Suite categories must be unique.")
        artifact_path = Path(self.artifact_path)
        if artifact_path.is_absolute() or ".." in artifact_path.parts:
            raise ValueError("Suite artifact_path must be repository-relative.")
        return self


class EvaluationCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["shopmind.evaluation-catalog.v1"]
    catalog_id: str = Field(min_length=1)
    required_categories: tuple[EvaluationCategory, ...]
    suites: tuple[CatalogSuite, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_manifest(self) -> "EvaluationCatalog":
        if tuple(self.required_categories) != REQUIRED_CATEGORIES:
            raise ValueError("Catalog required_categories contract is incomplete.")
        suite_ids = [suite.suite_id for suite in self.suites]
        runners = [suite.runner for suite in self.suites]
        artifact_paths = [suite.artifact_path for suite in self.suites]
        if len(set(suite_ids)) != len(suite_ids):
            raise ValueError("Catalog suite IDs must be unique.")
        if len(set(runners)) != len(runners):
            raise ValueError("Catalog runners must be unique.")
        if len(set(artifact_paths)) != len(artifact_paths):
            raise ValueError("Catalog artifact paths must be unique.")
        covered = {
            category
            for suite in self.suites
            if suite.required
            for category in suite.categories
        }
        missing = [
            category.value
            for category in REQUIRED_CATEGORIES
            if category not in covered
        ]
        if missing:
            raise ValueError(
                "Required evaluation categories are not covered: "
                + ", ".join(missing)
            )
        return self


class BaselineSuite(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact_schema: str
    total_cases: int = Field(ge=0)
    passed_cases: int = Field(ge=0)
    total_checks: int = Field(ge=0)
    passed_checks: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_counts(self) -> "BaselineSuite":
        if self.passed_cases > self.total_cases:
            raise ValueError("passed_cases cannot exceed total_cases.")
        if self.passed_checks > self.total_checks:
            raise ValueError("passed_checks cannot exceed total_checks.")
        return self


class RegressionThreshold(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    direction: Literal["min", "max"]
    allowed_delta: float = Field(default=0.0, ge=0.0)


REGRESSION_METRIC_DIRECTIONS: Mapping[str, Literal["min", "max"]] = {
    "quality_score": "min",
    "safety_score": "min",
    "latency_regression_count": "max",
    "token_regression_count": "max",
    "cost_regression_count": "max",
}


class AcceptedBaseline(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["shopmind.evaluation-baseline.v1"]
    baseline_id: str = Field(min_length=1)
    catalog_id: str = Field(min_length=1)
    catalog_schema_version: Literal["shopmind.evaluation-catalog.v1"]
    suites: dict[str, BaselineSuite]
    metrics: dict[str, float]
    thresholds: dict[str, RegressionThreshold]

    @model_validator(mode="after")
    def validate_metrics(self) -> "AcceptedBaseline":
        required_metrics = set(REGRESSION_METRIC_DIRECTIONS)
        if set(self.metrics) != required_metrics:
            raise ValueError("Baseline metric contract is incomplete.")
        if set(self.thresholds) != required_metrics:
            raise ValueError("Baseline threshold contract is incomplete.")
        for metric, direction in REGRESSION_METRIC_DIRECTIONS.items():
            if self.thresholds[metric].direction != direction:
                raise ValueError(f"Baseline direction is invalid for {metric}.")
        return self


class SuiteSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    suite_id: str
    artifact_schema: str
    categories: tuple[EvaluationCategory, ...]
    total_cases: int = Field(ge=0)
    passed_cases: int = Field(ge=0)
    pass_rate: float = Field(ge=0.0, le=1.0)
    total_checks: int = Field(ge=0)
    passed_checks: int = Field(ge=0)
    check_pass_rate: float = Field(ge=0.0, le=1.0)
    failures: list[dict[str, Any]]
    raw_summary: dict[str, Any]


def _router_summary() -> dict[str, Any]:
    summary = evaluate_supervisor_router(DeterministicSupervisorRouter())
    return {
        "schema_version": "shopmind.router-policy-eval.v1",
        "evaluation": "deterministic_router_policy",
        "total_cases": summary["total"],
        "passed_cases": summary["exact_matches"],
        "pass_rate": summary["exact_match_rate"],
        "total_checks": summary["total"],
        "passed_checks": summary["exact_matches"],
        "check_pass_rate": summary["exact_match_rate"],
        "fallback_count": summary["fallback_count"],
        "failures": summary["failures"],
    }


SUITE_RUNNERS: Mapping[RunnerName, Callable[[], dict[str, Any]]] = {
    "deterministic_router": _router_summary,
    "planner_policy": evaluate_planner_policy,
    "plan_trajectory": evaluate_plan_trajectories,
    "adapter_equivalence": evaluate_adapter_equivalence,
    "action_lifecycle": evaluate_action_lifecycle,
    "resilience_replay": evaluate_resilience_replay,
    "coordination_equivalence": evaluate_coordination_equivalence,
    "governance_lifecycle": evaluate_governance_lifecycle,
}


def load_catalog(path: Path = DEFAULT_CATALOG_PATH) -> EvaluationCatalog:
    try:
        return EvaluationCatalog.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise CatalogError("Evaluation catalog is invalid.") from exc


def load_baseline(path: Path = DEFAULT_BASELINE_PATH) -> AcceptedBaseline:
    try:
        return AcceptedBaseline.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise CatalogError("Accepted evaluation baseline is invalid.") from exc


def _summary_counts(summary: Mapping[str, Any]) -> tuple[int, int, int, int]:
    try:
        total_cases = int(summary["total_cases"])
        passed_cases = int(summary["passed_cases"])
        total_checks = int(summary["total_checks"])
        passed_checks = int(summary["passed_checks"])
    except (KeyError, TypeError, ValueError) as exc:
        raise CatalogError("Evaluation suite summary is missing stable counts.") from exc
    if min(total_cases, passed_cases, total_checks, passed_checks) < 0:
        raise CatalogError("Evaluation suite summary contains negative counts.")
    if passed_cases > total_cases or passed_checks > total_checks:
        raise CatalogError("Evaluation suite summary contains invalid counts.")
    return total_cases, passed_cases, total_checks, passed_checks


def _suite_snapshot(
    suite: CatalogSuite,
    summary: dict[str, Any],
) -> SuiteSnapshot:
    if summary.get("schema_version") != suite.artifact_schema:
        raise CatalogError(
            f"Evaluation suite '{suite.suite_id}' artifact schema does not match."
        )
    total_cases, passed_cases, total_checks, passed_checks = _summary_counts(summary)
    raw_failures = summary.get("failures", [])
    if not isinstance(raw_failures, list):
        raise CatalogError(
            f"Evaluation suite '{suite.suite_id}' failures must be a list."
        )
    failures = [
        failure
        if isinstance(failure, dict)
        else {"code": "evaluation.failure_invalid"}
        for failure in raw_failures
    ]
    return SuiteSnapshot(
        suite_id=suite.suite_id,
        artifact_schema=suite.artifact_schema,
        categories=suite.categories,
        total_cases=total_cases,
        passed_cases=passed_cases,
        pass_rate=passed_cases / total_cases if total_cases else 1.0,
        total_checks=total_checks,
        passed_checks=passed_checks,
        check_pass_rate=passed_checks / total_checks if total_checks else 1.0,
        failures=failures,
        raw_summary=summary,
    )


def _read_suite_artifact(path: Path, suite_id: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise CatalogError(
            f"Evaluation suite '{suite_id}' artifact is unreadable."
        ) from exc
    if not isinstance(payload, dict):
        raise CatalogError(
            f"Evaluation suite '{suite_id}' artifact must be an object."
        )
    return payload


def evaluate_catalog(
    catalog: EvaluationCatalog,
    *,
    artifacts_root: Path | None = None,
    reuse_existing: bool = False,
) -> dict[str, Any]:
    """Run or reuse only server-registered deterministic evaluation suites."""

    snapshots: list[SuiteSnapshot] = []
    for suite in catalog.suites:
        artifact_path = (
            artifacts_root / suite.artifact_path
            if artifacts_root is not None
            else None
        )
        if reuse_existing and artifact_path is not None and artifact_path.exists():
            summary = _read_suite_artifact(artifact_path, suite.suite_id)
        else:
            runner = SUITE_RUNNERS.get(suite.runner)
            if runner is None:
                raise CatalogError(
                    f"Evaluation suite '{suite.suite_id}' runner is not registered."
                )
            try:
                summary = runner()
            except Exception as exc:
                raise CatalogError(
                    f"Evaluation suite '{suite.suite_id}' execution failed."
                ) from exc
            if not isinstance(summary, dict):
                raise CatalogError(
                    f"Evaluation suite '{suite.suite_id}' result must be an object."
                )
            if artifact_path is not None:
                write_json_artifact(summary, artifact_path)
        snapshots.append(_suite_snapshot(suite, summary))

    total_cases = sum(snapshot.total_cases for snapshot in snapshots)
    passed_cases = sum(snapshot.passed_cases for snapshot in snapshots)
    total_checks = sum(snapshot.total_checks for snapshot in snapshots)
    passed_checks = sum(snapshot.passed_checks for snapshot in snapshots)
    category_suites: dict[EvaluationCategory, list[SuiteSnapshot]] = {
        category: [
            snapshot for snapshot in snapshots if category in snapshot.categories
        ]
        for category in REQUIRED_CATEGORIES
    }
    safety_suites = category_suites[EvaluationCategory.SAFETY]

    metrics = {
        "quality_score": passed_checks / total_checks if total_checks else 1.0,
        "safety_score": min(
            (snapshot.check_pass_rate for snapshot in safety_suites),
            default=0.0,
        ),
        "latency_regression_count": float(
            sum(
                len(snapshot.failures)
                for snapshot in category_suites[EvaluationCategory.LATENCY]
            )
        ),
        "token_regression_count": float(
            sum(
                len(snapshot.failures)
                for snapshot in category_suites[EvaluationCategory.TOKEN]
            )
        ),
        "cost_regression_count": float(
            sum(
                len(snapshot.failures)
                for snapshot in category_suites[EvaluationCategory.COST]
            )
        ),
    }
    return {
        "schema_version": "shopmind.evaluation-candidate.v1",
        "catalog_id": catalog.catalog_id,
        "catalog_schema_version": catalog.schema_version,
        "total_suites": len(snapshots),
        "passed_suites": sum(not snapshot.failures for snapshot in snapshots),
        "total_cases": total_cases,
        "passed_cases": passed_cases,
        "total_checks": total_checks,
        "passed_checks": passed_checks,
        "metrics": metrics,
        "suites": {
            snapshot.suite_id: snapshot.model_dump(mode="json")
            for snapshot in snapshots
        },
    }


def _comparison_check(
    check_id: str,
    *,
    passed: bool,
    candidate: Any,
    baseline: Any,
    allowed_delta: float | None = None,
) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "passed": passed,
        "candidate": candidate,
        "baseline": baseline,
        **(
            {"allowed_delta": allowed_delta}
            if allowed_delta is not None
            else {}
        ),
    }


def compare_candidate_to_baseline(
    catalog: EvaluationCatalog,
    candidate: Mapping[str, Any],
    baseline: AcceptedBaseline,
) -> dict[str, Any]:
    """Compare closed suite and metric contracts without accepting a new baseline."""

    checks: list[dict[str, Any]] = []
    checks.append(
        _comparison_check(
            "catalog_id",
            passed=(
                candidate.get("catalog_id") == baseline.catalog_id == catalog.catalog_id
            ),
            candidate=candidate.get("catalog_id"),
            baseline=baseline.catalog_id,
        )
    )
    checks.append(
        _comparison_check(
            "catalog_schema_version",
            passed=(
                candidate.get("catalog_schema_version")
                == baseline.catalog_schema_version
                == catalog.schema_version
            ),
            candidate=candidate.get("catalog_schema_version"),
            baseline=baseline.catalog_schema_version,
        )
    )

    candidate_suites = candidate.get("suites")
    if not isinstance(candidate_suites, Mapping):
        raise CatalogError("Candidate suites are invalid.")
    required_suite_ids = {suite.suite_id for suite in catalog.suites if suite.required}
    checks.append(
        _comparison_check(
            "required_suite_set",
            passed=(
                set(candidate_suites) == set(baseline.suites) == required_suite_ids
            ),
            candidate=sorted(candidate_suites),
            baseline=sorted(baseline.suites),
        )
    )
    for suite_id in sorted(required_suite_ids):
        raw_candidate_suite = candidate_suites.get(suite_id)
        baseline_suite = baseline.suites.get(suite_id)
        if not isinstance(raw_candidate_suite, Mapping) or baseline_suite is None:
            checks.append(
                _comparison_check(
                    f"suite:{suite_id}:present",
                    passed=False,
                    candidate=raw_candidate_suite is not None,
                    baseline=True,
                )
            )
            continue
        candidate_schema = raw_candidate_suite.get("artifact_schema")
        checks.append(
            _comparison_check(
                f"suite:{suite_id}:artifact_schema",
                passed=candidate_schema == baseline_suite.artifact_schema,
                candidate=candidate_schema,
                baseline=baseline_suite.artifact_schema,
            )
        )
        for count_name in (
            "total_cases",
            "passed_cases",
            "total_checks",
            "passed_checks",
        ):
            candidate_count = raw_candidate_suite.get(count_name)
            baseline_count = getattr(baseline_suite, count_name)
            checks.append(
                _comparison_check(
                    f"suite:{suite_id}:{count_name}",
                    passed=(
                        isinstance(candidate_count, int)
                        and not isinstance(candidate_count, bool)
                        and candidate_count >= baseline_count
                    ),
                    candidate=candidate_count,
                    baseline=baseline_count,
                )
            )

    candidate_metrics = candidate.get("metrics")
    if not isinstance(candidate_metrics, Mapping):
        raise CatalogError("Candidate metrics are invalid.")
    for metric, threshold in baseline.thresholds.items():
        candidate_value = candidate_metrics.get(metric)
        baseline_value = baseline.metrics[metric]
        valid_number = isinstance(candidate_value, (int, float)) and not isinstance(
            candidate_value, bool
        )
        passed = False
        if valid_number:
            numeric_candidate = float(candidate_value)
            if threshold.direction == "min":
                passed = numeric_candidate + threshold.allowed_delta >= baseline_value
            else:
                passed = numeric_candidate <= baseline_value + threshold.allowed_delta
        checks.append(
            _comparison_check(
                f"metric:{metric}",
                passed=passed,
                candidate=candidate_value,
                baseline=baseline_value,
                allowed_delta=threshold.allowed_delta,
            )
        )

    failures = [check for check in checks if not check["passed"]]
    return {
        "schema_version": "shopmind.evaluation-regression.v1",
        "baseline_id": baseline.baseline_id,
        "passed": not failures,
        "total_checks": len(checks),
        "passed_checks": len(checks) - len(failures),
        "failures": failures,
        "checks": checks,
    }


def evaluate_catalog_regression(
    *,
    catalog_path: Path = DEFAULT_CATALOG_PATH,
    baseline_path: Path = DEFAULT_BASELINE_PATH,
    artifacts_root: Path | None = None,
    reuse_existing: bool = False,
) -> dict[str, Any]:
    catalog = load_catalog(catalog_path)
    baseline = load_baseline(baseline_path)
    candidate = evaluate_catalog(
        catalog,
        artifacts_root=artifacts_root,
        reuse_existing=reuse_existing,
    )
    comparison = compare_candidate_to_baseline(catalog, candidate, baseline)
    suite_failures = [
        suite_id
        for suite_id, suite in candidate["suites"].items()
        if suite["failures"]
    ]
    passed = not suite_failures and comparison["passed"]
    return {
        "schema_version": "shopmind.evaluation-catalog-run.v1",
        "catalog_id": catalog.catalog_id,
        "baseline_id": baseline.baseline_id,
        "passed": passed,
        "suite_failures": suite_failures,
        "candidate": candidate,
        "comparison": comparison,
    }


def format_catalog_regression_summary(summary: Mapping[str, Any]) -> str:
    candidate = summary["candidate"]
    comparison = summary["comparison"]
    metrics = candidate["metrics"]
    failures = [
        *summary.get("suite_failures", []),
        *(failure["check_id"] for failure in comparison["failures"]),
    ]
    return "\n".join(
        (
            "# ShopMind V6 Evaluation Catalog Regression",
            "",
            f"- status: {'pass' if summary['passed'] else 'fail'}",
            f"- suites: {candidate['passed_suites']}/{candidate['total_suites']}",
            f"- cases: {candidate['passed_cases']}/{candidate['total_cases']}",
            f"- checks: {candidate['passed_checks']}/{candidate['total_checks']}",
            f"- quality score: {metrics['quality_score']:.6f}",
            f"- safety score: {metrics['safety_score']:.6f}",
            f"- comparison: {comparison['passed_checks']}/{comparison['total_checks']}",
            f"- regressions: {', '.join(failures) if failures else 'none'}",
        )
    )


__all__ = [
    "AcceptedBaseline",
    "CatalogError",
    "CatalogSuite",
    "DEFAULT_BASELINE_PATH",
    "DEFAULT_CATALOG_PATH",
    "EvaluationCatalog",
    "EvaluationCategory",
    "REQUIRED_CATEGORIES",
    "SUITE_RUNNERS",
    "compare_candidate_to_baseline",
    "evaluate_catalog",
    "evaluate_catalog_regression",
    "format_catalog_regression_summary",
    "load_baseline",
    "load_catalog",
]
