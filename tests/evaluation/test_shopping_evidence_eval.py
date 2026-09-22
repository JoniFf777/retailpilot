from evaluation.run_shopping_evidence_eval import run_cases


def test_shopping_evidence_business_gate_passes():
    report = run_cases()
    assert report["passed"] == report["total"]
