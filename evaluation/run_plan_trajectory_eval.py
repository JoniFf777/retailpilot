r"""Run the model-independent ShopMind V5 graph trajectory replay evaluation.

Usage:
    conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe evaluation/run_plan_trajectory_eval.py
    conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe evaluation/run_plan_trajectory_eval.py --json
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from evaluation.json_artifacts import write_json_artifact
from evaluation.shopmind_plan_trajectory_eval import (
    evaluate_plan_trajectories,
    format_plan_trajectory_summary,
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Replay fixed ShopMind graph plan trajectories."
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
    summary = evaluate_plan_trajectories()
    if args.output_json is not None:
        write_json_artifact(summary, args.output_json)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(format_plan_trajectory_summary(summary))
    return 0 if not summary["failures"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
