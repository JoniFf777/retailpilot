"""Validate the closed ShopMind production-profile configuration contract."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from app.core.settings import Settings
from app.operations import evaluate_production_preflight
from evaluation.json_artifacts import write_json_artifact


def _format_summary(report: dict) -> str:
    failures = [
        check["check_id"]
        for check in report["checks"]
        if check["status"] == "failed"
    ]
    return "\n".join(
        (
            "# ShopMind Production Configuration Preflight",
            "",
            f"- profile: {report['profile']}",
            f"- status: {report['status']}",
            f"- checks: {report['passed_checks']}/{report['total_checks']}",
            f"- failures: {', '.join(failures) if failures else 'none'}",
        )
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate ShopMind production configuration without probes."
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args(argv)

    try:
        settings = Settings.from_env()
    except Exception:
        print("ShopMind production preflight: settings_invalid")
        return 1

    report = evaluate_production_preflight(settings).model_dump(mode="json")
    if args.output_json:
        write_json_artifact(report, args.output_json)
    print(
        json.dumps(report, ensure_ascii=False, indent=2)
        if args.json
        else _format_summary(report)
    )
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
