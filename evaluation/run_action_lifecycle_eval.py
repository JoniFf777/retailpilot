"""Run the model-independent ShopMind generic action lifecycle gate."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from evaluation.json_artifacts import write_json_artifact
from evaluation.shopmind_action_lifecycle_eval import (
    evaluate_action_lifecycle,
    format_action_lifecycle_summary,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args(argv)
    summary = evaluate_action_lifecycle()
    if args.output_json:
        write_json_artifact(summary, args.output_json)
    print(
        json.dumps(summary, ensure_ascii=False, indent=2)
        if args.json
        else format_action_lifecycle_summary(summary)
    )
    return 0 if not summary["failures"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
