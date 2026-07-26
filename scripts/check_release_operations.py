"""Evaluate a captured rollout, rollback, or incident operations envelope."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from app.operations import ReleaseOperationInput, evaluate_release_operation
from evaluation.json_artifacts import write_json_artifact


def _format_summary(report: dict) -> str:
    failed = [
        check["check_id"]
        for check in report["checks"]
        if check["status"] == "failed"
    ]
    waiting = [
        check["check_id"]
        for check in report["checks"]
        if check["status"] == "waiting"
    ]
    return "\n".join(
        (
            "# ShopMind Release Operations Check",
            "",
            f"- operation: {report['operation']}",
            f"- status: {report['status']}",
            f"- recommended_action: {report['recommended_action']}",
            f"- checks: {report['passed_checks']}/{report['total_checks']}",
            f"- failed: {', '.join(failed) if failed else 'none'}",
            f"- waiting: {', '.join(waiting) if waiting else 'none'}",
        )
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate captured ShopMind health contracts without network "
            "access, database mutation, or migration downgrade."
        )
    )
    parser.add_argument("--input-json", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args(argv)

    try:
        evidence = ReleaseOperationInput.model_validate_json(
            args.input_json.read_text(encoding="utf-8")
        )
        report = evaluate_release_operation(evidence).model_dump(mode="json")
    except Exception:
        print("ShopMind release operations check: input_invalid")
        return 1

    if args.output_json:
        write_json_artifact(report, args.output_json)
    print(
        json.dumps(report, ensure_ascii=False, indent=2)
        if args.json
        else _format_summary(report)
    )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
