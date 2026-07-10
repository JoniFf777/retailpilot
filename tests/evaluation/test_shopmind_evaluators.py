from evaluation.shopmind_evaluators import (
    debug_metadata_evaluator,
    expected_keywords_evaluator,
    expected_routes_evaluator,
    expected_tools_evaluator,
    forbidden_tools_evaluator,
    status_evaluator,
)
from evaluation.create_shopmind_dataset import (
    SHOPMIND_V3_ROUTER_EXAMPLES,
    V3_ROUTER_DATASET_NAME,
)
from evaluation.run_langsmith_eval import (
    V1_EVAL_TARGET,
    V3_ROUTER_EVAL_TARGET,
    build_evaluators as build_langsmith_evaluators,
    resolve_eval_config,
)
from evaluation.shopmind_router_eval import (
    ROUTER_EVAL_CASES,
    evaluate_supervisor_router,
)
from evaluation.run_router_eval import evaluate_v3_router_target, build_router, main


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


def test_expected_routes_evaluator_reads_routes_from_debug_metadata() -> None:
    result = expected_routes_evaluator(
        inputs={},
        outputs={
            "debug": {
                "supervisor_decision": {
                    "routes": ["product_agent", "rag_agent"],
                }
            }
        },
        reference_outputs={"expected_routes": ["rag_agent", "product_agent"]},
    )

    assert result["score"] is True


def test_debug_metadata_evaluator_passes_with_supervisor_trace() -> None:
    result = debug_metadata_evaluator(
        inputs={},
        outputs={
            "debug": {
                "supervisor_decision": {
                    "routes": ["product_agent"],
                    "router_type": "deterministic",
                },
                "agent_steps": [
                    {
                        "index": 1,
                        "node": "supervisor",
                        "event": "routed",
                    }
                ],
            }
        },
        reference_outputs={"expected_routes": ["product_agent"]},
    )

    assert result["score"] is True


def test_debug_metadata_evaluator_fails_when_debug_missing() -> None:
    result = debug_metadata_evaluator(
        inputs={},
        outputs={"answer": "missing debug"},
        reference_outputs={},
    )

    assert result["score"] is False
    assert "Missing supervisor_decision" in result["comment"]
    assert "agent_steps is missing or empty" in result["comment"]


def test_debug_metadata_evaluator_reports_route_mismatch() -> None:
    result = debug_metadata_evaluator(
        inputs={},
        outputs={
            "debug": {
                "supervisor_decision": {
                    "routes": ["product_agent"],
                    "router_type": "deterministic",
                },
                "agent_steps": [
                    {
                        "index": 1,
                        "node": "supervisor",
                        "event": "routed",
                    }
                ],
            }
        },
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


def test_run_router_eval_cli_prints_deterministic_summary(capsys) -> None:
    exit_code = main(["--router", "deterministic"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "ShopMind router eval" in output
    assert "router: deterministic" in output
    assert "exact matches: 6/6 (100.0%)" in output
    assert "failures: none" in output


def test_run_router_eval_cli_prints_json_summary(capsys) -> None:
    exit_code = main(["--router", "deterministic", "--json"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert '"total": 6' in output
    assert '"exact_match_rate": 1.0' in output


def test_run_router_eval_llm_fallback_mode_uses_unconfigured_router() -> None:
    router = build_router("llm-fallback")

    summary = evaluate_supervisor_router(router=router)

    assert summary["exact_match_rate"] == 1.0
    assert summary["fallback_count"] == len(ROUTER_EVAL_CASES)


def test_run_router_eval_target_mode_scores_fake_target(capsys, monkeypatch) -> None:
    def fake_target(inputs: dict) -> dict:
        return {
            "status": "completed",
            "debug": {
                "supervisor_decision": {
                    "routes": ["product_agent"],
                    "router_type": "deterministic",
                },
                "agent_steps": [
                    {
                        "index": 1,
                        "node": "supervisor",
                        "event": "routed",
                    }
                ],
            },
        }

    monkeypatch.setattr("evaluation.run_router_eval.ROUTER_EVAL_CASES", (
        {
            "name": "fake_product",
            "message": "推荐键盘",
            "user_id": "USER-001",
            "expected_routes": ["product_agent"],
        },
    ))
    monkeypatch.setattr("evaluation.run_router_eval.shopmind_v3_router_target", fake_target)

    exit_code = main(["--mode", "target"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "ShopMind V3 router target eval" in output
    assert "checks: 3/3 (100.0%)" in output
    assert "failures: none" in output


def test_evaluate_v3_router_target_reports_evaluator_failure() -> None:
    def fake_target(inputs: dict) -> dict:
        return {
            "status": "completed",
            "debug": {
                "supervisor_decision": {
                    "routes": ["product_agent"],
                    "router_type": "deterministic",
                },
                "agent_steps": [
                    {
                        "index": 1,
                        "node": "supervisor",
                        "event": "routed",
                    }
                ],
            },
        }

    summary = evaluate_v3_router_target(
        target_fn=fake_target,
        cases=(
            {
                "name": "needs_rag",
                "message": "退货政策",
                "expected_routes": ["rag_agent"],
            },
        ),
    )

    assert summary["passed_checks"] == 1
    assert summary["total_checks"] == 3
    assert summary["failures"][0]["case"] == "needs_rag"
    assert summary["failures"][0]["evaluator"] == "expected_routes"
    assert summary["failures"][1]["evaluator"] == "debug_metadata"


def test_v3_router_dataset_examples_include_expected_routes() -> None:
    assert len(SHOPMIND_V3_ROUTER_EXAMPLES) == len(ROUTER_EVAL_CASES)
    assert all(
        example["inputs"]["include_debug"] is True
        and example["outputs"]["expected_status"] == "completed"
        and example["outputs"]["expected_routes"]
        for example in SHOPMIND_V3_ROUTER_EXAMPLES
    )


def test_run_langsmith_eval_keeps_v1_evaluators_by_default() -> None:
    evaluators = build_langsmith_evaluators(target=V1_EVAL_TARGET)

    assert expected_tools_evaluator in evaluators
    assert expected_routes_evaluator not in evaluators
    assert debug_metadata_evaluator not in evaluators


def test_run_langsmith_eval_builds_v3_router_evaluators() -> None:
    evaluators = build_langsmith_evaluators(target=V3_ROUTER_EVAL_TARGET)
    config = resolve_eval_config(V3_ROUTER_EVAL_TARGET)

    assert evaluators == [
        status_evaluator,
        expected_routes_evaluator,
        debug_metadata_evaluator,
    ]
    assert config["dataset"] == V3_ROUTER_DATASET_NAME
    assert config["experiment_prefix"] == "shopmind-v3-router"


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
