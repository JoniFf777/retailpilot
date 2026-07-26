r"""Run the model-independent ShopMind V5 planner policy evaluation.

Usage:
    conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe evaluation/run_planner_eval.py
    conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe evaluation/run_planner_eval.py --json
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from evaluation.json_artifacts import write_json_artifact
from evaluation.shopmind_planner_eval import (
    evaluate_planner_policy,
    format_planner_eval_summary,
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run fixed offline checks for the ShopMind planner boundary."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the raw evaluation summary as JSON.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        help="Write the raw evaluation summary to this JSON file.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    summary = evaluate_planner_policy()
    if args.output_json is not None:
        write_json_artifact(summary, args.output_json)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(format_planner_eval_summary(summary))
    return 0 if not summary["failures"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
