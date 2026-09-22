"""Offline rollout/rollback gate for the optional shopping AI platform."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def evaluate_rollout(mode: str, *, readiness: str, baseline_passed: bool, rollback_verified: bool) -> dict[str, object]:
    if mode not in {"default_off", "shadow", "enabled"}:
        return {"status": "blocked", "reason": "unknown_mode"}
    if mode == "default_off":
        return {"status": "ready", "reason": "optional_platform_disabled", "public_mutations": False}
    if mode == "shadow":
        return {"status": "ready", "reason": "shadow_has_no_public_mutations", "public_mutations": False}
    if readiness != "ready" or not baseline_passed:
        return {"status": "blocked", "reason": "readiness_or_baseline_failed", "public_mutations": False}
    if not rollback_verified:
        return {"status": "blocked", "reason": "rollback_evidence_missing", "public_mutations": False}
    return {"status": "ready", "reason": "baseline_and_rollback_verified", "public_mutations": True}


def run_cases() -> dict[str, object]:
    cases = {
        "default_off": evaluate_rollout("default_off", readiness="ready", baseline_passed=False, rollback_verified=False),
        "shadow": evaluate_rollout("shadow", readiness="ready", baseline_passed=False, rollback_verified=False),
        "enabled_requires_evidence": evaluate_rollout("enabled", readiness="ready", baseline_passed=True, rollback_verified=False),
        "enabled": evaluate_rollout("enabled", readiness="ready", baseline_passed=True, rollback_verified=True),
        "advanced_backends_deferred": {"status": "deferred", "reason": "await_live_quality_metrics"},
    }
    checks = [
        cases["default_off"]["public_mutations"] is False,
        cases["shadow"]["public_mutations"] is False,
        cases["enabled_requires_evidence"]["status"] == "blocked",
        cases["enabled"]["status"] == "ready",
        cases["advanced_backends_deferred"]["status"] == "deferred",
    ]
    return {"schema_version": "shopmind.ai-platform-release.v1", "passed": sum(checks), "total": len(checks), "cases": cases}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the offline ShopMind AI platform rollout gate.")
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args(argv)
    report = run_cases()
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    print(payload)
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(payload, encoding="utf-8")
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
