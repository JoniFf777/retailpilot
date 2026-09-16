from evaluation.run_simulated_eval import run_quality, run_retrieval


def test_simulated_suite_is_explicitly_labelled_and_reproducible() -> None:
    quality = run_quality()
    retrieval = run_retrieval()
    assert quality["simulated"] is True
    assert quality["task_count"] == 20
    assert quality["metrics"]["task_success_rate"] == 1.0
    assert retrieval["simulated"] is True
    assert retrieval["case_count"] == 12
    assert retrieval["metrics"]["recall_at_k"] == 1.0
