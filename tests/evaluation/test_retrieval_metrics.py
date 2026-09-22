import pytest

from evaluation.retrieval_metrics import (
    aggregate_retrieval_metrics,
    evaluate_retrieval_case,
)


def test_retrieval_metrics_use_unique_evidence_ids_and_rank() -> None:
    result = evaluate_retrieval_case(
        ["doc-a", "doc-a", "doc-c", "doc-b"],
        ["doc-b", "doc-c"],
        k=4,
    )
    assert result.hit_at_k == 1.0
    assert result.recall_at_k == 1.0
    assert result.reciprocal_rank == pytest.approx(1 / 3)


def test_retrieval_metrics_fail_closed_for_empty_labels_or_suite() -> None:
    with pytest.raises(ValueError):
        evaluate_retrieval_case(["doc-a"], [], k=5)
    with pytest.raises(ValueError):
        aggregate_retrieval_metrics([])
