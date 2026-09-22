from evaluation.run_ai_runtime_resilience_eval import run_cases


def test_ai_runtime_resilience_gate_passes():
    report = run_cases()
    assert report["passed"] == report["total"]
