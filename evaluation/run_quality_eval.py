"""Aggregate independent captured task outcomes into a quality report."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from evaluation.json_artifacts import write_json_artifact
from evaluation.quality_metrics import TaskOutcome, aggregate_quality_metrics


def evaluate_file(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw_outcomes = payload.get("outcomes") if isinstance(payload, dict) else None
    if not isinstance(raw_outcomes, list) or not raw_outcomes:
        raise ValueError("quality evaluation requires a non-empty outcomes list")
    outcomes = [TaskOutcome(**item) for item in raw_outcomes if isinstance(item, dict)]
    if len(outcomes) != len(raw_outcomes):
        raise ValueError("each quality outcome must be an object")
    metrics = aggregate_quality_metrics(outcomes)
    return {
        "schema_version": "shopmind.quality-eval.v1",
        "task_count": len(outcomes),
        "metrics": asdict(metrics),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Aggregate captured quality outcomes.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = evaluate_file(args.input)
        report["execution_ok"] = True
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        report = {
            "schema_version": "shopmind.quality-eval.v1",
            "execution_ok": False,
            "quality_passed": False,
            "error": {
                "code": "quality_eval_invalid",
                "message": "Quality evaluation input is invalid.",
            },
        }
    if args.output_json:
        write_json_artifact(report, args.output_json)
    print(
        json.dumps(report, ensure_ascii=False, indent=2)
        if args.json
        else json.dumps(report.get("metrics", {}), ensure_ascii=False)
    )
    return 0 if report.get("execution_ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
