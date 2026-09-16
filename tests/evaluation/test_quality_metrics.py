import pytest

from evaluation.quality_metrics import TaskOutcome, aggregate_quality_metrics


def test_quality_metrics_keep_execution_and_quality_separate() -> None:
    report = aggregate_quality_metrics(
        [
            TaskOutcome(
                task_id="a",
                execution_ok=True,
                quality_passed=True,
                required_constraint_count=2,
                correct_constraint_count=2,
                recommendation_count=2,
                required_evidence_count=1,
                supported_evidence_count=1,
                latency_ms=100,
                total_tokens=20,
            ),
            TaskOutcome(
                task_id="b",
                execution_ok=True,
                quality_passed=False,
                required_constraint_count=2,
                correct_constraint_count=1,
                recommendation_count=1,
                hard_constraint_violation_count=1,
                required_evidence_count=1,
                supported_evidence_count=0,
                latency_ms=300,
                total_tokens=40,
            ),
        ]
    )
    assert report.execution_success_rate == 1.0
    assert report.task_success_rate == 0.5
    assert report.constraint_accuracy == pytest.approx(0.75)
    assert report.hard_constraint_violation_rate == pytest.approx(1 / 3)
    assert report.evidence_recall == 0.5
    assert report.mean_latency_ms == 200
    assert report.p50_latency_ms == 100
    assert report.p95_latency_ms == 300


def test_quality_metrics_reject_empty_suite() -> None:
    with pytest.raises(ValueError):
        aggregate_quality_metrics([])
