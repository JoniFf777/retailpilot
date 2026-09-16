"""Outcome-level metrics for captured ShopMind recommendation tasks.

The evaluator deliberately consumes facts produced by a run and independent
labels. It does not infer quality from the answer string alone.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from statistics import mean
from typing import Sequence


@dataclass(frozen=True)
class TaskOutcome:
    task_id: str
    execution_ok: bool
    quality_passed: bool
    required_constraint_count: int = 0
    correct_constraint_count: int = 0
    recommendation_count: int = 0
    hard_constraint_violation_count: int = 0
    required_evidence_count: int = 0
    supported_evidence_count: int = 0
    latency_ms: float | None = None
    total_tokens: int | None = None
    cost_usd: float | None = None


@dataclass(frozen=True)
class QualityMetrics:
    task_success_rate: float
    execution_success_rate: float
    constraint_accuracy: float | None
    hard_constraint_violation_rate: float
    evidence_recall: float | None
    mean_latency_ms: float | None
    p50_latency_ms: float | None
    p95_latency_ms: float | None
    mean_total_tokens: float | None
    mean_cost_usd: float | None


def _ratio(numerator: int, denominator: int) -> float | None:
    return None if denominator <= 0 else numerator / denominator


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(len(ordered) * percentile) - 1))
    return ordered[index]


def aggregate_quality_metrics(outcomes: Sequence[TaskOutcome]) -> QualityMetrics:
    """Aggregate independent task outcomes without treating retries as tasks."""

    if not outcomes:
        raise ValueError("at least one task outcome is required")
    latency = [item.latency_ms for item in outcomes if item.latency_ms is not None]
    tokens = [item.total_tokens for item in outcomes if item.total_tokens is not None]
    costs = [item.cost_usd for item in outcomes if item.cost_usd is not None]
    return QualityMetrics(
        task_success_rate=mean(item.quality_passed for item in outcomes),
        execution_success_rate=mean(item.execution_ok for item in outcomes),
        constraint_accuracy=_ratio(
            sum(item.correct_constraint_count for item in outcomes),
            sum(item.required_constraint_count for item in outcomes),
        ),
        hard_constraint_violation_rate=_ratio(
            sum(item.hard_constraint_violation_count for item in outcomes),
            sum(item.recommendation_count for item in outcomes),
        ) or 0.0,
        evidence_recall=_ratio(
            sum(item.supported_evidence_count for item in outcomes),
            sum(item.required_evidence_count for item in outcomes),
        ),
        mean_latency_ms=None if not latency else mean(latency),
        p50_latency_ms=_percentile(latency, 0.50),
        p95_latency_ms=_percentile(latency, 0.95),
        mean_total_tokens=None if not tokens else mean(tokens),
        mean_cost_usd=None if not costs else mean(costs),
    )


__all__ = ["QualityMetrics", "TaskOutcome", "aggregate_quality_metrics"]
