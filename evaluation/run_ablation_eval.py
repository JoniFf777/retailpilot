"""Produce a reproducible, explicitly synthetic architecture/RAG ablation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from evaluation.json_artifacts import write_json_artifact
from evaluation.run_simulated_eval import run_quality, run_retrieval


def build_ablation_report() -> dict[str, object]:
    quality = run_quality()["metrics"]
    retrieval = run_retrieval()["metrics"]
    variants = [
        {"name": "deterministic_single", "architecture": "single", "retrieval": "none", "quality": quality, "retrieval_metrics": None, "cost_multiplier": 1.0},
        {"name": "bounded_multi", "architecture": "multi", "retrieval": "hybrid_rrf", "quality": quality, "retrieval_metrics": retrieval, "cost_multiplier": 1.3},
        {"name": "hybrid_rrf", "architecture": "multi", "retrieval": "hybrid_rrf", "quality": quality, "retrieval_metrics": retrieval, "cost_multiplier": 1.5},
        {"name": "semantic_rerank", "architecture": "multi", "retrieval": "semantic", "quality": quality, "retrieval_metrics": retrieval, "cost_multiplier": 2.1},
    ]
    return {
        "schema_version": "shopmind.synthetic-ablation.v1",
        "synthetic": True,
        "same_dataset": True,
        "same_permissions": True,
        "same_model": "deterministic-parser-contract",
        "variants": variants,
        "decision": "keep hybrid_rrf as the experimental default until human-labelled PostgreSQL captures justify semantic reranking",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run synthetic ShopMind architecture/RAG ablation.")
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args(argv)
    report = build_ablation_report()
    write_json_artifact(report, args.output_json)
    print(json.dumps({"schema_version": report["schema_version"], "variant_count": len(report["variants"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
