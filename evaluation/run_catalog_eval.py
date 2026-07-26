"""Run the model-independent ShopMind V6 evaluation catalog gate."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from evaluation.json_artifacts import write_json_artifact
from evaluation.shopmind_catalog_eval import (
    CatalogError,
    DEFAULT_BASELINE_PATH,
    DEFAULT_CATALOG_PATH,
    evaluate_catalog_regression,
    format_catalog_regression_summary,
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the versioned offline evaluation catalog and baseline gate."
    )
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG_PATH)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE_PATH)
    parser.add_argument("--artifacts-root", type=Path)
    parser.add_argument("--reuse-existing", action="store_true")
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.reuse_existing and args.artifacts_root is None:
        parser.error("--reuse-existing requires --artifacts-root")
    return args


def _failure_summary(error_code: str) -> dict[str, Any]:
    return {
        "schema_version": "shopmind.evaluation-catalog-run.v1",
        "passed": False,
        "error": {"code": error_code, "message": "Evaluation catalog gate failed."},
        "suite_failures": [],
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        summary = evaluate_catalog_regression(
            catalog_path=args.catalog,
            baseline_path=args.baseline,
            artifacts_root=args.artifacts_root,
            reuse_existing=args.reuse_existing,
        )
    except CatalogError:
        summary = _failure_summary("evaluation.catalog_invalid")
    if args.output_json is not None:
        write_json_artifact(summary, args.output_json)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    elif "candidate" in summary:
        print(format_catalog_regression_summary(summary))
    else:
        print("ShopMind V6 evaluation catalog: failed (evaluation.catalog_invalid)")
    return 0 if summary.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
