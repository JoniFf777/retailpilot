"""Sanitized connectivity probe for the shopping task planner/reviewer."""

from __future__ import annotations

import argparse
from time import perf_counter

from app.ai_platform.contracts import ModelOperation
from app.ai_platform.model_registry import default_model_registry
from app.core.settings import get_settings
from app.shopping_tasks.contracts import GoalSpec, VerificationReport
from app.shopping_tasks.model_gateway import _invoke_review_structured, _invoke_structured
from app.shopping_tasks.planner import offline_plan


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("planner", "reviewer"))
    args = parser.parse_args()
    settings = get_settings()
    operation = ModelOperation.PLANNER if args.operation == "planner" else ModelOperation.DECISION
    candidate = default_model_registry(settings).snapshot.for_operation(operation)[0].model_copy(
        update={"total_timeout_ms": 180_000}
    )
    goal = GoalSpec(kind="compatibility_diagnosis", goal_text="扩展坞连接显示器后没有画面")
    started = perf_counter()
    try:
        if args.operation == "planner":
            result = _invoke_structured(candidate, goal, offline_plan(goal))
            outcome = {"reason": result.reason, "steps": len(result.steps)}
        else:
            result = _invoke_review_structured(
                candidate,
                goal,
                VerificationReport(status="pass"),
                {"diagnostic_check": {"outcome": "resolved"}},
            )
            outcome = {"status": result.status, "issues": len(result.issues)}
    except Exception as exc:
        print({"passed": False, "error_type": type(exc).__name__, "seconds": round(perf_counter() - started, 1)})
        return 1
    print({"passed": True, "seconds": round(perf_counter() - started, 1), **outcome})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
