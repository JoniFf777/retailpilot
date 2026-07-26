"""Run the model-independent ShopMind resilience and restart replay gate."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from evaluation.json_artifacts import write_json_artifact
from evaluation.shopmind_resilience_replay_eval import (
    evaluate_resilience_replay,
    format_resilience_replay_summary,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args(argv)
    summary = evaluate_resilience_replay()
    if args.output_json:
        write_json_artifact(summary, args.output_json)
    print(
        json.dumps(summary, ensure_ascii=False, indent=2)
        if args.json
        else format_resilience_replay_summary(summary)
    )
    return 0 if not summary["failures"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
