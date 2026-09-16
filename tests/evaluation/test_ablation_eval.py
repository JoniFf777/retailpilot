from evaluation.run_ablation_eval import build_ablation_report


def test_ablation_report_keeps_variants_and_tradeoff_disclosure() -> None:
    report = build_ablation_report()
    assert report["synthetic"] is True
    assert report["same_dataset"] is True
    assert {item["name"] for item in report["variants"]} == {
        "deterministic_single", "bounded_multi", "hybrid_rrf", "semantic_rerank"
    }
    assert "human-labelled" in report["decision"]
