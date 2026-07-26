"""Run the deterministic ShopMind coordination backend gate."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from evaluation.json_artifacts import write_json_artifact
from evaluation.shopmind_coordination_eval import evaluate_coordination_equivalence


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run deterministic local/Redis coordination equivalence."
    )
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    summary = evaluate_coordination_equivalence()
    if args.output_json is not None:
        write_json_artifact(summary, args.output_json)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(
            "ShopMind coordination equivalence: "
            f"{summary['passed_cases']}/{summary['total_cases']} cases, "
            f"{summary['passed_checks']}/{summary['total_checks']} checks"
        )
    return 0 if not summary["failures"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
