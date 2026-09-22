from evaluation.run_retrieval_equivalence_eval import run_cases


def test_retrieval_equivalence_gate_passes():
    report = run_cases()
    assert report["passed"] == report["total"]
