"""Run a small, deterministic contract benchmark without a model or database.

The suite is deliberately labelled as ``simulated``.  It exercises request
extraction, bounded recommendation contracts and retrieval metric plumbing;
it is not a substitute for human labels or a PostgreSQL capture.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from time import perf_counter
from typing import Any

from app.recommendation.request import parse_recommendation_request
from evaluation.json_artifacts import write_json_artifact
from evaluation.quality_metrics import TaskOutcome, aggregate_quality_metrics
from evaluation.retrieval_metrics import (
    aggregate_retrieval_metrics,
    evaluate_retrieval_case,
)


QUALITY_CASES: tuple[dict[str, Any], ...] = (
    {
        "case_id": "q01",
        "category": "laptop",
        "message": "预算6000元以内，16GB内存，1.5kg重量",
        "budget_max": "6000",
        "attributes": {"memory_min_gb": "16", "weight_max_kg": "1.5"},
    },
    {
        "case_id": "q02",
        "category": "laptop",
        "message": "预算5000到8000元，32GB内存",
        "budget_min": "5000",
        "budget_max": "8000",
        "attributes": {"memory_min_gb": "32"},
    },
    {
        "case_id": "q03",
        "category": "laptop",
        "message": "预算7000元，办公用途，不要独显",
        "budget_max": "7000",
        "attributes": {
            "gpu_tier_min": {"value": "rtx4050", "polarity": "exclude"},
            "primary_use_cases": {"value": ["office"], "polarity": "include"},
        },
    },
    {
        "case_id": "q04",
        "category": "laptop",
        "message": "预算6500元，Java开发，16GB内存",
        "budget_max": "6500",
        "attributes": {
            "memory_min_gb": "16",
            "primary_use_cases": {"value": ["java_development"], "polarity": "include"},
        },
    },
    {
        "case_id": "q05",
        "category": "laptop",
        "message": "预算8000元，32GB内存，2kg以下",
        "budget_max": "8000",
        "attributes": {"memory_min_gb": "32", "weight_max_kg": "2"},
    },
    {
        "case_id": "q06",
        "category": "laptop",
        "message": "预算4000元，办公，512GB存储",
        "budget_max": "4000",
        "attributes": {
            "storage_min_gb": "512",
            "primary_use_cases": {"value": ["office"], "polarity": "include"},
        },
    },
    {
        "case_id": "q07",
        "category": "monitor",
        "message": "预算3000元，27英寸，144Hz",
        "budget_max": "3000",
        "attributes": {"size_min_inches": "27", "refresh_rate_min_hz": "144"},
    },
    {
        "case_id": "q08",
        "category": "monitor",
        "message": "预算2500元，2K分辨率，办公用途",
        "budget_max": "2500",
        "attributes": {
            "resolution_min": {"value": "1440p"},
            "use_case": {"value": "office"},
        },
    },
    {
        "case_id": "q09",
        "category": "monitor",
        "message": "预算5000元，OLED面板，设计用途",
        "budget_max": "5000",
        "attributes": {
            "panel_type": {"value": "oled"},
            "use_case": {"value": "design"},
        },
    },
    {
        "case_id": "q10",
        "category": "phone",
        "message": "预算5000元，12GB内存，256GB存储",
        "budget_max": "5000",
        "attributes": {"memory_min_gb": "12", "storage_min_gb": "256"},
    },
    {
        "case_id": "q11",
        "category": "phone",
        "message": "预算3000元，5G网络，拍照用途",
        "budget_max": "3000",
        "attributes": {
            "connectivity": {"value": "5g"},
            "use_case": {"value": ["photo"]},
        },
    },
    {
        "case_id": "q12",
        "category": "phone",
        "message": "预算4000元，电池5000mAh，6.5英寸屏幕",
        "budget_max": "4000",
        "attributes": {"battery_min_mah": "5000", "screen_min_inches": "6.5"},
    },
    {
        "case_id": "q13",
        "category": "headphones",
        "message": "预算1500元，蓝牙连接，续航30小时",
        "budget_max": "1500",
        "attributes": {"connectivity": {"value": "bluetooth"}, "battery_hours": "30"},
    },
    {
        "case_id": "q14",
        "category": "headphones",
        "message": "预算1000元，头戴，音乐用途",
        "budget_max": "1000",
        "attributes": {
            "form_factor": {"value": "over_ear"},
            "use_case": {"value": ["music"]},
        },
    },
    {
        "case_id": "q15",
        "category": "keyboard",
        "message": "预算500元，机械键盘，办公用途",
        "budget_max": "500",
        "attributes": {"use_case": {"value": ["office"]}},
    },
    {
        "case_id": "q16",
        "category": "mouse",
        "message": "预算300元，游戏用途",
        "budget_max": "300",
        "attributes": {"use_case": {"value": ["gaming"]}},
    },
    {
        "case_id": "q17",
        "category": "camera",
        "message": "预算8000元，旅行用途",
        "budget_max": "8000",
        "attributes": {"use_case": {"value": ["travel"]}},
    },
    {
        "case_id": "q18",
        "category": "router",
        "message": "预算600元，家用用途",
        "budget_max": "600",
        "attributes": {"use_case": {"value": ["home"]}},
    },
    {
        "case_id": "q19",
        "category": "tablet",
        "message": "预算3500元，学习用途，10英寸",
        "budget_max": "3500",
        "attributes": {"use_case": {"value": ["study"]}, "screen_min_inches": "10"},
    },
    {
        "case_id": "q20",
        "category": "speaker",
        "message": "预算1200元，家用用途",
        "budget_max": "1200",
        "attributes": {"use_case": {"value": ["home"]}},
    },
)


RETRIEVAL_CASES: tuple[dict[str, Any], ...] = (
    {"case_id": "r01", "ranked": ["usb4", "usb3", "return"], "relevant": ["usb4"]},
    {
        "case_id": "r02",
        "ranked": ["return", "warranty", "usb4"],
        "relevant": ["return"],
    },
    {
        "case_id": "r03",
        "ranked": ["warranty", "return", "usb4"],
        "relevant": ["warranty"],
    },
    {"case_id": "r04", "ranked": ["quiet", "fan", "return"], "relevant": ["quiet"]},
    {"case_id": "r05", "ranked": ["fan", "quiet", "warranty"], "relevant": ["fan"]},
    {
        "case_id": "r06",
        "ranked": ["waterproof", "return", "usb4"],
        "relevant": ["waterproof"],
    },
    {
        "case_id": "r07",
        "ranked": ["shipping", "return", "warranty"],
        "relevant": ["shipping"],
    },
    {
        "case_id": "r08",
        "ranked": ["compatibility", "usb4", "return"],
        "relevant": ["compatibility"],
    },
    {
        "case_id": "r09",
        "ranked": ["return", "shipping", "warranty"],
        "relevant": ["return", "shipping"],
    },
    {
        "case_id": "r10",
        "ranked": ["warranty", "return", "shipping"],
        "relevant": ["warranty", "return"],
    },
    {
        "case_id": "r11",
        "ranked": ["quiet", "compatibility", "fan"],
        "relevant": ["quiet", "fan"],
    },
    {
        "case_id": "r12",
        "ranked": ["usb4", "compatibility", "warranty"],
        "relevant": ["usb4", "compatibility"],
    },
)


def _canonical(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _canonical(item) for key, item in sorted(value.items())}
    if isinstance(value, list):
        return sorted(_canonical(item) for item in value)
    return str(value) if value is not None else None


def run_quality() -> dict[str, Any]:
    outcomes: list[TaskOutcome] = []
    cases: list[dict[str, Any]] = []
    for case in QUALITY_CASES:
        started = perf_counter()
        request = parse_recommendation_request(case["message"], case["category"])
        actual_attributes = {
            key: {"value": constraint.value, "polarity": constraint.polarity}
            for key, constraint in request.category_attributes.items()
        }
        expected_attributes = case.get("attributes", {})
        required = (
            len(expected_attributes)
            + int("budget_max" in case)
            + int("budget_min" in case)
        )

        def expected_constraint(value: Any) -> dict[str, Any]:
            if isinstance(value, dict):
                return {
                    "value": value.get("value"),
                    "polarity": value.get("polarity", "include"),
                }
            return {"value": value, "polarity": "include"}

        correct = sum(
            _canonical(actual_attributes.get(key))
            == _canonical(expected_constraint(value))
            for key, value in expected_attributes.items()
        )
        if "budget_max" in case:
            correct += int(
                _canonical(request.budget_max) == _canonical(case["budget_max"])
            )
        if "budget_min" in case:
            correct += int(
                _canonical(request.budget_min) == _canonical(case["budget_min"])
            )
        execution_ok = True
        quality_passed = correct == required
        outcome = TaskOutcome(
            task_id=case["case_id"],
            execution_ok=execution_ok,
            quality_passed=quality_passed,
            required_constraint_count=required,
            correct_constraint_count=correct,
            recommendation_count=1,
            hard_constraint_violation_count=0,
            latency_ms=(perf_counter() - started) * 1000,
            total_tokens=max(1, len(case["message"]) // 4),
        )
        outcomes.append(outcome)
        cases.append(
            {
                "case_id": case["case_id"],
                "quality_passed": quality_passed,
                "required": required,
                "correct": correct,
                "actual_attributes": _canonical(actual_attributes),
            }
        )
    return {
        "schema_version": "shopmind.simulated-quality.v1",
        "simulated": True,
        "task_count": len(outcomes),
        "metrics": aggregate_quality_metrics(outcomes).__dict__,
        "cases": cases,
    }


def run_retrieval() -> dict[str, Any]:
    results = [
        evaluate_retrieval_case(case["ranked"], case["relevant"], k=3)
        for case in RETRIEVAL_CASES
    ]
    return {
        "schema_version": "shopmind.simulated-retrieval.v1",
        "simulated": True,
        "case_count": len(results),
        "metrics": aggregate_retrieval_metrics(results).__dict__,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the deterministic simulated ShopMind benchmark."
    )
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = {"quality": run_quality(), "retrieval": run_retrieval()}
    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        write_json_artifact(report["quality"], args.output_dir / "quality.json")
        write_json_artifact(report["retrieval"], args.output_dir / "retrieval.json")
    print(
        json.dumps(report, ensure_ascii=False, indent=2)
        if args.json
        else json.dumps(
            {
                "quality": report["quality"]["metrics"],
                "retrieval": report["retrieval"]["metrics"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
