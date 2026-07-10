"""Offline route evaluation helpers for the ShopMind multi-agent supervisor."""

from typing import Any, NotRequired, TypedDict

from agents.shopmind_multi_agent.supervisor_router import (
    DeterministicSupervisorRouter,
    SupervisorRouter,
)


class RouterEvalCase(TypedDict):
    name: str
    message: str
    expected_routes: list[str]
    user_id: NotRequired[str | None]


class RouterEvalFailure(TypedDict):
    name: str
    message: str
    expected_routes: list[str]
    actual_routes: list[str]
    missing_routes: list[str]
    unexpected_routes: list[str]
    router_type: str | None
    fallback_reason: NotRequired[str]


class RouterEvalSummary(TypedDict):
    total: int
    exact_matches: int
    exact_match_rate: float
    fallback_count: int
    fallback_rate: float
    failures: list[RouterEvalFailure]


ROUTER_EVAL_CASES: tuple[RouterEvalCase, ...] = (
    {
        "name": "product_recommendation",
        "message": "推荐一个适合办公的键盘",
        "user_id": "USER-001",
        "expected_routes": ["product_agent"],
    },
    {
        "name": "policy_question",
        "message": "退货政策和保修规则是什么",
        "user_id": "USER-001",
        "expected_routes": ["rag_agent"],
    },
    {
        "name": "preference_with_user",
        "message": "根据我的偏好推荐一个显示器",
        "user_id": "USER-001",
        "expected_routes": ["product_agent", "preference_agent"],
    },
    {
        "name": "preference_without_user",
        "message": "我的偏好适合什么耳机",
        "user_id": None,
        "expected_routes": ["product_agent"],
    },
    {
        "name": "mixed_product_policy_preference",
        "message": "结合我的偏好推荐键盘，并看看退货政策",
        "user_id": "USER-001",
        "expected_routes": ["product_agent", "rag_agent", "preference_agent"],
    },
    {
        "name": "fallback_general_browse",
        "message": "随便看看",
        "user_id": None,
        "expected_routes": ["product_agent"],
    },
)


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value]
    return [str(value)]


def _routes_from_outputs(outputs: dict) -> list[str]:
    debug = outputs.get("debug")
    if isinstance(debug, dict):
        supervisor_decision = debug.get("supervisor_decision")
        if isinstance(supervisor_decision, dict):
            routes = supervisor_decision.get("routes")
            if routes is not None:
                return _as_list(routes)
        routes = debug.get("routes")
        if routes is not None:
            return _as_list(routes)

    supervisor_decision = outputs.get("supervisor_decision")
    if isinstance(supervisor_decision, dict):
        routes = supervisor_decision.get("routes")
        if routes is not None:
            return _as_list(routes)
    return _as_list(outputs.get("routes"))


def compare_routes(expected_routes: list[str], actual_routes: list[str]) -> dict:
    """Compare route sets while preserving readable missing/unexpected lists."""
    expected_set = set(expected_routes)
    actual_set = set(actual_routes)
    missing_routes = [route for route in expected_routes if route not in actual_set]
    unexpected_routes = [route for route in actual_routes if route not in expected_set]

    return {
        "score": not missing_routes and not unexpected_routes,
        "missing_routes": missing_routes,
        "unexpected_routes": unexpected_routes,
    }


def expected_routes_evaluator(
    inputs: dict,
    outputs: dict,
    reference_outputs: dict,
) -> dict:
    """Check whether supervisor routes match expected read-agent routes."""
    expected_routes = _as_list(reference_outputs.get("expected_routes"))
    actual_routes = _routes_from_outputs(outputs)
    comparison = compare_routes(expected_routes, actual_routes)

    return {
        "key": "expected_routes",
        "score": comparison["score"],
        "comment": (
            "Routes matched."
            if comparison["score"]
            else (
                f"Missing routes: {comparison['missing_routes']}. "
                f"Unexpected routes: {comparison['unexpected_routes']}. "
                f"Actual routes: {actual_routes}."
            )
        ),
    }


def evaluate_supervisor_router(
    router: SupervisorRouter | None = None,
    cases: tuple[RouterEvalCase, ...] = ROUTER_EVAL_CASES,
) -> RouterEvalSummary:
    """Run a deterministic offline route check over a fixed sample set."""
    active_router = router or DeterministicSupervisorRouter()
    failures: list[RouterEvalFailure] = []
    exact_matches = 0
    fallback_count = 0

    for case in cases:
        decision = active_router.route(case["message"], user_id=case.get("user_id"))
        actual_routes = _as_list(decision.get("routes"))
        expected_routes = case["expected_routes"]
        comparison = compare_routes(expected_routes, actual_routes)

        if comparison["score"]:
            exact_matches += 1
        else:
            failure: RouterEvalFailure = {
                "name": case["name"],
                "message": case["message"],
                "expected_routes": expected_routes,
                "actual_routes": actual_routes,
                "missing_routes": comparison["missing_routes"],
                "unexpected_routes": comparison["unexpected_routes"],
                "router_type": decision.get("router_type"),
            }
            fallback_reason = decision.get("fallback_reason")
            if fallback_reason:
                failure["fallback_reason"] = str(fallback_reason)
            failures.append(failure)

        if decision.get("router_type") == "llm_fallback" or decision.get(
            "fallback_used"
        ):
            fallback_count += 1

    total = len(cases)
    return {
        "total": total,
        "exact_matches": exact_matches,
        "exact_match_rate": exact_matches / total if total else 0.0,
        "fallback_count": fallback_count,
        "fallback_rate": fallback_count / total if total else 0.0,
        "failures": failures,
    }


__all__ = [
    "ROUTER_EVAL_CASES",
    "RouterEvalCase",
    "RouterEvalFailure",
    "RouterEvalSummary",
    "compare_routes",
    "evaluate_supervisor_router",
    "expected_routes_evaluator",
]
