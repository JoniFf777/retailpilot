from evaluation.shopmind_evaluators import (
    debug_metadata_evaluator,
    expected_keywords_evaluator,
    expected_routes_evaluator,
    expected_tools_evaluator,
    forbidden_tools_evaluator,
    pending_action_evaluator,
    status_evaluator,
)
from evaluation.shopmind_event_reporting import (
    event_summary_metric_rows,
    extract_debug_events,
    format_event_metrics,
    format_event_summary,
    summarize_debug_events,
)
from evaluation.shopmind_handoff_eval import (
    evaluate_v3_handoff_target,
    format_handoff_summary,
    run_handoff_case,
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


def test_debug_metadata_evaluator_accepts_write_guardrail_empty_routes() -> None:
    result = debug_metadata_evaluator(
        inputs={},
        outputs={
            "debug": {
                "supervisor_decision": {
                    "intent": "write_path_unsupported",
                    "routes": [],
                    "router_type": "deterministic",
                    "safety_flags": ["write_intent_blocked"],
                },
                "decision": {"answer_type": "write_path_handoff"},
                "safety_flags": ["write_intent_blocked"],
                "agent_steps": [
                    {
                        "index": 1,
                        "node": "supervisor",
                        "event": "routed",
                    }
                ],
            }
        },
        reference_outputs={
            "expected_routes": [],
            "expected_intent": "write_path_unsupported",
            "expected_answer_type": "write_path_handoff",
            "expected_safety_flags": ["write_intent_blocked"],
        },
    )

    assert result["score"] is True


def test_debug_metadata_evaluator_reports_write_guardrail_mismatch() -> None:
    result = debug_metadata_evaluator(
        inputs={},
        outputs={
            "debug": {
                "supervisor_decision": {
                    "intent": "read_path",
                    "routes": ["product_agent"],
                    "router_type": "deterministic",
                },
                "decision": {"answer_type": "product_read_summary"},
                "agent_steps": [
                    {
                        "index": 1,
                        "node": "supervisor",
                        "event": "routed",
                    }
                ],
            }
        },
        reference_outputs={
            "expected_routes": [],
            "expected_intent": "write_path_unsupported",
            "expected_answer_type": "write_path_handoff",
            "expected_safety_flags": ["write_intent_blocked"],
        },
    )

    assert result["score"] is False
    assert "Intent mismatch" in result["comment"]
    assert "Answer type mismatch" in result["comment"]
    assert "Missing safety flags" in result["comment"]


def test_extract_debug_events_reads_write_handoff_and_confirmation_events() -> None:
    events = extract_debug_events(
        {
            "debug": {
                "write_handoff_debug": {
                    "candidate_context": {
                        "events": [
                            {
                                "index": 1,
                                "event": "candidate_context_stored",
                                "candidate_count": 2,
                            }
                        ]
                    }
                },
                "confirmation": {
                    "events": [
                        {
                            "index": 1,
                            "event": "pending_action_confirmed",
                            "status": "completed",
                        }
                    ]
                },
            }
        }
    )

    assert events == [
        {
            "event": "candidate_context_stored",
            "group": "candidate_context",
            "source": "debug.write_handoff_debug.candidate_context",
            "metadata": {"candidate_count": 2},
        },
        {
            "event": "pending_action_confirmed",
            "group": "confirmation",
            "source": "debug.confirmation",
            "metadata": {"status": "completed"},
        },
    ]


def test_summarize_debug_events_reports_counts_and_rates() -> None:
    summary = summarize_debug_events(
        [
            {
                "debug": {
                    "candidate_context": {
                        "events": [
                            {"event": "candidate_context_missed"},
                            {"event": "candidate_context_stored"},
                        ]
                    }
                }
            },
            {
                "debug": {
                    "confirmation": {
                        "events": [{"event": "pending_action_cancelled"}]
                    }
                }
            },
            {"debug": {}},
        ]
    )

    assert summary["total_outputs"] == 3
    assert summary["outputs_with_events"] == 2
    assert summary["output_event_rate"] == 2 / 3
    assert summary["total_events"] == 3
    assert summary["group_counts"] == {"candidate_context": 2, "confirmation": 1}
    assert summary["event_counts"] == {
        "candidate_context_missed": 1,
        "candidate_context_stored": 1,
        "pending_action_cancelled": 1,
    }
    assert summary["group_rates"] == {
        "candidate_context": 2 / 3,
        "confirmation": 1 / 3,
    }


def test_format_event_summary_handles_empty_event_set() -> None:
    summary = summarize_debug_events([{"debug": {}}, {"answer": "no debug"}])

    output = format_event_summary(summary)

    assert "outputs: 2" in output
    assert "event counts: none" in output


def test_event_summary_metric_rows_flatten_operational_counters() -> None:
    summary = summarize_debug_events(
        [
            {
                "debug": {
                    "write_handoff_debug": {
                        "candidate_context": {
                            "events": [{"event": "candidate_context_stored"}]
                        }
                    }
                }
            },
            {
                "debug": {
                    "confirmation": {
                        "events": [{"event": "pending_action_failed"}]
                    }
                }
            },
        ]
    )

    rows = event_summary_metric_rows(summary, prefix="shopmind_test")

    assert {
        "name": "shopmind_test_outputs_total",
        "labels": {},
        "value": 2.0,
    } in rows
    assert {
        "name": "shopmind_test_group_events_total",
        "labels": {"group": "candidate_context"},
        "value": 1.0,
    } in rows
    assert {
        "name": "shopmind_test_events_by_name_total",
        "labels": {
            "event": "pending_action_failed",
            "group": "confirmation",
        },
        "value": 1.0,
    } in rows


def test_format_event_metrics_prints_prometheus_style_samples() -> None:
    summary = summarize_debug_events(
        [
            {
                "debug": {
                    "write_handoff_debug": {
                        "candidate_context": {
                            "events": [{"event": "candidate_context_stored"}]
                        }
                    }
                }
            }
        ]
    )

    output = format_event_metrics(summary, prefix="shopmind_test")

    assert "shopmind_test_outputs_total 1" in output
    assert "shopmind_test_events_total 1" in output
    assert (
        'shopmind_test_events_by_name_total{event="candidate_context_stored",'
        'group="candidate_context"} 1'
    ) in output
    assert (
        'shopmind_test_events_per_output{event="candidate_context_stored",'
        'group="candidate_context"} 1'
    ) in output


def test_router_eval_cases_cover_core_read_routes() -> None:
    expected_case_names = {
        "product_recommendation",
        "policy_question",
        "preference_with_user",
        "preference_without_user",
        "mixed_product_policy_preference",
        "fallback_general_browse",
        "write_missing_product_id_guardrail",
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
    assert "exact matches: 7/7 (100.0%)" in output
    assert "failures: none" in output


def test_run_router_eval_cli_prints_json_summary(capsys) -> None:
    exit_code = main(["--router", "deterministic", "--json"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert '"total": 7' in output
    assert '"exact_match_rate": 1.0' in output


def test_run_router_eval_llm_fallback_mode_uses_unconfigured_router() -> None:
    router = build_router("llm-fallback")

    summary = evaluate_supervisor_router(router=router)

    assert summary["exact_match_rate"] == 1.0
    assert summary["fallback_count"] == len(ROUTER_EVAL_CASES) - 1


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
    assert "checks: 6/6 (100.0%)" in output
    assert "failures: none" in output


def test_run_router_eval_handoff_mode_scores_fake_summary(capsys, monkeypatch) -> None:
    monkeypatch.setattr(
        "evaluation.run_router_eval.evaluate_v3_handoff_target",
        lambda: {
            "total_cases": 1,
            "passed_cases": 1,
            "pass_rate": 1.0,
            "event_summary": summarize_debug_events(
                [
                    {
                        "debug": {
                            "confirmation": {
                                "events": [{"event": "pending_action_confirmed"}]
                            }
                        }
                    }
                ]
            ),
            "case_results": [],
            "failures": [],
        },
    )

    exit_code = main(["--mode", "handoff"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "ShopMind V3 API handoff eval" in output
    assert "pending_action_confirmed" in output
    assert "failures: none" in output


def test_run_router_eval_handoff_mode_prints_event_metrics(
    capsys,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "evaluation.run_router_eval.evaluate_v3_handoff_target",
        lambda: {
            "total_cases": 1,
            "passed_cases": 1,
            "pass_rate": 1.0,
            "event_summary": summarize_debug_events(
                [
                    {
                        "debug": {
                            "confirmation": {
                                "events": [{"event": "pending_action_confirmed"}]
                            }
                        }
                    }
                ]
            ),
            "case_results": [],
            "failures": [],
        },
    )

    exit_code = main(["--mode", "handoff", "--event-metrics"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "ShopMind V3 API handoff eval" not in output
    assert "shopmind_v3_debug_events_total 1" in output
    assert (
        'shopmind_v3_debug_events_by_name_total{event="pending_action_confirmed",'
        'group="confirmation"} 1'
    ) in output


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

    assert summary["passed_checks"] == 4
    assert summary["total_checks"] == 6
    assert summary["failures"][0]["case"] == "needs_rag"
    assert summary["failures"][0]["evaluator"] == "expected_routes"
    assert summary["failures"][1]["evaluator"] == "debug_metadata"


def test_evaluate_v3_router_target_includes_event_summary() -> None:
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
                "write_handoff_debug": {
                    "candidate_context": {
                        "events": [{"event": "candidate_context_stored"}]
                    }
                },
            },
        }

    summary = evaluate_v3_router_target(
        target_fn=fake_target,
        cases=(
            {
                "name": "product_with_event",
                "message": "鎺ㄨ崘閿洏",
                "expected_routes": ["product_agent"],
            },
        ),
    )

    assert summary["event_summary"]["total_outputs"] == 1
    assert summary["event_summary"]["event_counts"] == {
        "candidate_context_stored": 1
    }


def test_run_handoff_case_confirms_pending_action_with_events() -> None:
    def fake_chat_fn(
        message: str,
        user_id: str | None = None,
        thread_id: str | None = None,
    ):
        return {
            "status": "confirmation_required",
            "pending_action_id": "pending-001",
            "debug": {
                "write_handoff_debug": {
                    "candidate_context": {
                        "events": [{"event": "candidate_context_selected"}]
                    }
                }
            },
        }

    def fake_confirm_fn(pending_action_id: str, user_id: str, confirmed: bool):
        return {
            "status": "completed",
            "pending_action_id": pending_action_id,
            "debug": {
                "confirmation": {
                    "events": [{"event": "pending_action_confirmed"}]
                }
            },
        }

    result = run_handoff_case(
        {
            "name": "confirm",
            "message": "add TECH-KEY-001",
            "user_id": "user-001",
            "thread_id": "thread-001",
            "confirm": True,
            "expected_chat_status": "confirmation_required",
            "expected_confirm_status": "completed",
            "expected_chat_events": ["candidate_context_selected"],
            "expected_confirm_events": ["pending_action_confirmed"],
        },
        chat_fn=fake_chat_fn,
        confirm_fn=fake_confirm_fn,
    )

    assert result["passed"] is True
    assert result["event_summary"]["event_counts"] == {
        "candidate_context_selected": 1,
        "pending_action_confirmed": 1,
    }


def test_evaluate_v3_handoff_target_aggregates_cases_and_events() -> None:
    def fake_chat_fn(
        message: str,
        user_id: str | None = None,
        thread_id: str | None = None,
    ):
        if "TECH-KEY-001" in message:
            return {
                "status": "confirmation_required",
                "pending_action_id": "pending-001",
                "debug": {},
            }
        return {
            "status": "completed",
            "pending_action_id": None,
            "debug": {
                "write_handoff_debug": {
                    "candidate_context": {
                        "events": [{"event": "candidate_context_stored"}]
                    }
                }
            },
        }

    def fake_confirm_fn(pending_action_id: str, user_id: str, confirmed: bool):
        return {
            "status": "completed",
            "pending_action_id": pending_action_id,
            "debug": {
                "confirmation": {
                    "events": [{"event": "pending_action_confirmed"}]
                }
            },
        }

    summary = evaluate_v3_handoff_target(
        chat_fn=fake_chat_fn,
        confirm_fn=fake_confirm_fn,
    )

    assert summary["passed_cases"] == 2
    assert summary["total_cases"] == 2
    assert summary["failures"] == []
    assert summary["event_summary"]["event_counts"] == {
        "candidate_context_stored": 1,
        "pending_action_confirmed": 1,
    }


def test_format_handoff_summary_reports_failures() -> None:
    output = format_handoff_summary(
        {
            "passed_cases": 0,
            "total_cases": 1,
            "pass_rate": 0.0,
            "event_summary": summarize_debug_events([]),
            "failures": [{"case": "broken", "failures": ["missing event"]}],
        }
    )

    assert "ShopMind V3 API handoff eval" in output
    assert "broken" in output
    assert "missing event" in output


def test_v3_router_dataset_examples_include_expected_routes() -> None:
    assert len(SHOPMIND_V3_ROUTER_EXAMPLES) == len(ROUTER_EVAL_CASES)
    assert all(
        example["inputs"]["include_debug"] is True
        and example["outputs"]["expected_status"] == "completed"
        and "expected_routes" in example["outputs"]
        for example in SHOPMIND_V3_ROUTER_EXAMPLES
    )
    write_case = next(
        example
        for example in SHOPMIND_V3_ROUTER_EXAMPLES
        if example["metadata"]["case"] == "write_missing_product_id_guardrail"
    )
    assert write_case["outputs"]["expected_routes"] == []
    assert write_case["outputs"]["expected_intent"] == "write_path_unsupported"
    assert write_case["outputs"]["expected_pending_action_present"] is False


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
        forbidden_tools_evaluator,
        expected_keywords_evaluator,
        pending_action_evaluator,
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


def test_pending_action_evaluator_passes_when_absent_as_expected() -> None:
    result = pending_action_evaluator(
        inputs={},
        outputs={"pending_action_id": None},
        reference_outputs={"expected_pending_action_present": False},
    )

    assert result["score"] is True


def test_pending_action_evaluator_fails_when_unexpected_pending_action_exists() -> None:
    result = pending_action_evaluator(
        inputs={},
        outputs={"pending_action_id": "pending-001"},
        reference_outputs={"expected_pending_action_present": False},
    )

    assert result["score"] is False
    assert "Expected pending_action_id presence" in result["comment"]


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
