"""Run the offline retrieval-only metric over labelled JSON cases.

Input format::

    {"cases": [{"case_id": "...", "retrieved_ids": [...],
                "relevant_ids": [...]}], "k": 5}

The command never calls a model or a database.  It is intended to consume
captured results from a real PostgreSQL retrieval run and keep Recall/MRR
diagnostics independent from generation scoring.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from evaluation.json_artifacts import write_json_artifact
from evaluation.retrieval_metrics import (
    aggregate_retrieval_metrics,
    evaluate_retrieval_case,
)


def evaluate_file(path: Path, *, default_k: int = 5) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = payload.get("cases") if isinstance(payload, dict) else None
    if not isinstance(cases, list) or not cases:
        raise ValueError("retrieval evaluation requires a non-empty cases list")
    metrics = []
    case_outputs = []
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise ValueError("each retrieval case must be an object")
        case_id = str(case.get("case_id") or f"case-{index + 1}")
        k = int(case.get("k") or payload.get("k") or default_k)
        result = evaluate_retrieval_case(
            case.get("retrieved_ids") or case.get("retrieved_doc_ids") or [],
            case.get("relevant_ids") or case.get("relevant_doc_ids") or [],
            k=k,
        )
        metrics.append(result)
        case_outputs.append({"case_id": case_id, "k": k, **result.__dict__})
    aggregate = aggregate_retrieval_metrics(metrics)
    return {
        "schema_version": "shopmind.retrieval-eval.v1",
        "case_count": len(case_outputs),
        "metrics": aggregate.__dict__,
        "cases": case_outputs,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run deterministic retrieval metrics.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = evaluate_file(args.input)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        report = {
            "schema_version": "shopmind.retrieval-eval.v1",
            "passed": False,
            "error": {"code": "retrieval_eval_invalid", "message": "Retrieval evaluation input is invalid."},
        }
    else:
        report["passed"] = True
    if args.output_json:
        write_json_artifact(report, args.output_json)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif report.get("passed"):
        print(json.dumps(report["metrics"], ensure_ascii=False))
    else:
        print("ShopMind retrieval evaluation: invalid input")
    return 0 if report.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
