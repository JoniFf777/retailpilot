from evaluation.run_ai_platform_release_eval import run_cases


def test_ai_platform_release_gate_passes():
    report = run_cases()
    assert report["passed"] == report["total"]
