r"""Run the model-independent ShopMind adapter equivalence evaluation."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from evaluation.json_artifacts import write_json_artifact
from evaluation.shopmind_adapter_equivalence_eval import (
    evaluate_adapter_equivalence,
    format_adapter_equivalence_summary,
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate local and HTTP specialist adapter contracts."
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output-json", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    summary = evaluate_adapter_equivalence()
    if args.output_json is not None:
        write_json_artifact(summary, args.output_json)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(format_adapter_equivalence_summary(summary))
    return 0 if not summary["failures"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
