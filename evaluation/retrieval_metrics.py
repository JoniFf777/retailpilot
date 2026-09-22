"""Small, deterministic retrieval metrics for the ShopMind evidence path.

These metrics operate on stable document or fact identifiers rather than chunk
text.  That prevents overlapping chunks from inflating a recall score and keeps
retrieval quality separate from answer-generation quality.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from typing import Sequence


@dataclass(frozen=True)
class RetrievalCaseMetrics:
    hit_at_k: float
    recall_at_k: float
    reciprocal_rank: float


def _normalized_ids(values: Sequence[str]) -> list[str]:
    return [
        str(value).strip()
        for value in values
        if value is not None and str(value).strip()
    ]


def evaluate_retrieval_case(
    retrieved_ids: Sequence[str],
    relevant_ids: Sequence[str],
    *,
    k: int,
) -> RetrievalCaseMetrics:
    """Score one ranked result against independently labelled evidence IDs."""

    if k <= 0:
        raise ValueError("k must be positive")
    relevant = set(_normalized_ids(relevant_ids))
    if not relevant:
        raise ValueError("relevant_ids must contain at least one evidence ID")
    ranked = _normalized_ids(retrieved_ids)
    top_k = ranked[:k]
    hits = [item for item in top_k if item in relevant]
    first_rank = next(
        (index for index, item in enumerate(top_k, start=1) if item in relevant),
        None,
    )
    return RetrievalCaseMetrics(
        hit_at_k=float(bool(hits)),
        recall_at_k=len(set(hits)) / len(relevant),
        reciprocal_rank=0.0 if first_rank is None else 1.0 / first_rank,
    )


def aggregate_retrieval_metrics(
    cases: Sequence[RetrievalCaseMetrics],
) -> RetrievalCaseMetrics:
    """Macro-average case metrics; empty suites fail closed."""

    if not cases:
        raise ValueError("at least one retrieval case is required")
    return RetrievalCaseMetrics(
        hit_at_k=mean(case.hit_at_k for case in cases),
        recall_at_k=mean(case.recall_at_k for case in cases),
        reciprocal_rank=mean(case.reciprocal_rank for case in cases),
    )


__all__ = [
    "RetrievalCaseMetrics",
    "aggregate_retrieval_metrics",
    "evaluate_retrieval_case",
]
