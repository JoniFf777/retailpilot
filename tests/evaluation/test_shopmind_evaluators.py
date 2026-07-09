from evaluation.shopmind_evaluators import (
    expected_keywords_evaluator,
    expected_routes_evaluator,
    expected_tools_evaluator,
    forbidden_tools_evaluator,
    status_evaluator,
)
from evaluation.shopmind_router_eval import (
    ROUTER_EVAL_CASES,
    evaluate_supervisor_router,
)


def test_expected_routes_evaluator_passes_when_routes_match() -> None:
    result = expected_routes_evaluator(
        inputs={},
        outputs={"supervisor_decision": {"routes": ["product_agent", "rag_agent"]}},
        reference_outputs={"expected_routes": ["rag_agent", "product_agent"]},
    )

    assert result["score"] is True


def test_expected_routes_evaluator_fails_when_route_missing() -> None:
    result = expected_routes_evaluator(
        inputs={},
        outputs={"routes": ["product_agent"]},
        reference_outputs={"expected_routes": ["product_agent", "rag_agent"]},
    )

    assert result["score"] is False
    assert "rag_agent" in result["comment"]


def test_router_eval_cases_cover_core_read_routes() -> None:
    expected_case_names = {
        "product_recommendation",
        "policy_question",
        "preference_with_user",
        "preference_without_user",
        "mixed_product_policy_preference",
        "fallback_general_browse",
    }

    assert {case["name"] for case in ROUTER_EVAL_CASES} == expected_case_names


def test_evaluate_supervisor_router_scores_deterministic_baseline() -> None:
    summary = evaluate_supervisor_router()

    assert summary["total"] == len(ROUTER_EVAL_CASES)
    assert summary["exact_matches"] == summary["total"]
    assert summary["exact_match_rate"] == 1.0
    assert summary["fallback_count"] == 1
    assert summary["failures"] == []


def test_evaluate_supervisor_router_reports_failures() -> None:
    class ProductOnlyRouter:
        def route(self, message: str, user_id: str | None = None) -> dict:
            return {
                "intent": "read_path",
                "routes": ["product_agent"],
                "routing_reasons": {"product_agent": "forced_product"},
                "confidence": "low",
                "fallback_used": False,
                "requires_user_id_for_preferences": False,
                "router_type": "test",
            }

    summary = evaluate_supervisor_router(router=ProductOnlyRouter())

    assert summary["exact_matches"] < summary["total"]
    assert summary["failures"]
    assert any(
        "rag_agent" in failure["missing_routes"] for failure in summary["failures"]
    )


def test_expected_tools_evaluator_passes_when_all_expected_tools_called() -> None:
    result = expected_tools_evaluator(
        inputs={},
        outputs={"tool_calls": ["search_products", "get_user_preferences"]},
        reference_outputs={"expected_tools": ["search_products"]},
    )

    assert result["score"] is True


def test_expected_tools_evaluator_fails_when_tool_missing() -> None:
    result = expected_tools_evaluator(
        inputs={},
        outputs={"tool_calls": ["search_products"]},
        reference_outputs={"expected_tools": ["search_products", "compare_products"]},
    )

    assert result["score"] is False
    assert "compare_products" in result["comment"]


def test_forbidden_tools_evaluator_passes_when_forbidden_tools_absent() -> None:
    result = forbidden_tools_evaluator(
        inputs={},
        outputs={"tool_calls": ["prepare_add_to_cart"]},
        reference_outputs={"forbidden_tools": ["confirm_add_to_cart"]},
    )

    assert result["score"] is True


def test_forbidden_tools_evaluator_fails_when_forbidden_tool_called() -> None:
    result = forbidden_tools_evaluator(
        inputs={},
        outputs={"tool_calls": ["confirm_add_to_cart"]},
        reference_outputs={"forbidden_tools": ["confirm_add_to_cart"]},
    )

    assert result["score"] is False
    assert "confirm_add_to_cart" in result["comment"]


def test_status_evaluator_passes_when_status_matches() -> None:
    result = status_evaluator(
        inputs={},
        outputs={"status": "confirmation_required"},
        reference_outputs={"expected_status": "confirmation_required"},
    )

    assert result["score"] is True


def test_status_evaluator_fails_when_status_differs() -> None:
    result = status_evaluator(
        inputs={},
        outputs={"status": "completed"},
        reference_outputs={"expected_status": "confirmation_required"},
    )

    assert result["score"] is False
    assert "confirmation_required" in result["comment"]


def test_expected_keywords_evaluator_passes_when_all_keywords_present() -> None:
    result = expected_keywords_evaluator(
        inputs={},
        outputs={"answer": "我已为你生成待确认加购，请确认是否加入购物车。"},
        reference_outputs={"expected_keywords": ["确认", "购物车"]},
    )

    assert result["score"] is True


def test_expected_keywords_evaluator_fails_when_keyword_missing() -> None:
    result = expected_keywords_evaluator(
        inputs={},
        outputs={"answer": "我推荐这款键盘。"},
        reference_outputs={"expected_keywords": ["购物车"]},
    )

    assert result["score"] is False
    assert "购物车" in result["comment"]
