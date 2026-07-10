from langchain_core.tools import tool

from agents.shopmind_multi_agent import (
    build_multi_agent_debug_metadata,
    create_shopmind_multi_agent_graph,
)
from agents.shopmind_multi_agent.decision_agent import decision_agent_node
from agents.shopmind_multi_agent.permissions import guard_tool, tools_by_name
from agents.shopmind_multi_agent.supervisor import (
    build_supervisor_decision,
    determine_routes,
)
from agents.shopmind_multi_agent.supervisor_router import (
    LLMSupervisorRouterInput,
    LLMSupervisorRouterOutput,
    LLMSupervisorRouter,
    create_langchain_supervisor_decision_provider,
    create_supervisor_router,
)


@tool("search_products")
def fake_search_products(query: str, limit: int = 5) -> str:
    """Fake product search."""
    return "找到 1 个符合条件的商品：测试键盘（TECH-KEY-001）。RAW_PRODUCT_DETAIL_SHOULD_NOT_LEAK"


@tool("search_product_docs")
def fake_search_product_docs(query: str) -> str:
    """Fake product docs."""
    return "测试键盘支持蓝牙连接。"


@tool("search_policy_docs")
def fake_search_policy_docs(query: str) -> str:
    """Fake policy docs."""
    return "退货政策：30 天内可退货。"


@tool("get_user_preferences")
def fake_get_user_preferences(user_id: str) -> str:
    """Fake preference read."""
    return f"用户 {user_id} 的购物偏好： 1. 风格（style）：安静键盘。RAW_PREFERENCE_SHOULD_NOT_LEAK"


def _graph():
    product_tools = tools_by_name([guard_tool("product_agent", fake_search_products)])
    rag_tools = tools_by_name(
        [
            guard_tool("rag_agent", fake_search_product_docs),
            guard_tool("rag_agent", fake_search_policy_docs),
        ]
    )
    preference_tools = tools_by_name(
        [guard_tool("preference_agent", fake_get_user_preferences)]
    )
    return create_shopmind_multi_agent_graph(
        product_tools=product_tools,
        rag_tools=rag_tools,
        preference_tools=preference_tools,
    )


class RagOnlyTestRouter:
    def route(self, message: str, user_id: str | None = None) -> dict:
        return {
            "intent": "read_path",
            "routes": ["rag_agent"],
            "routing_reasons": {"rag_agent": "test_router_forced_rag"},
            "confidence": "low",
            "fallback_used": False,
            "requires_user_id_for_preferences": False,
            "router_type": "test",
        }


class FakeStructuredRouterModel:
    def __init__(self, output: dict) -> None:
        self.output = output
        self.messages = None

    def invoke(self, messages: list[dict[str, str]]) -> dict:
        self.messages = messages
        return self.output


class FakeChatModel:
    def __init__(self, output: dict) -> None:
        self.output = output
        self.schema = None
        self.structured_model: FakeStructuredRouterModel | None = None

    def with_structured_output(self, schema):
        self.schema = schema
        self.structured_model = FakeStructuredRouterModel(self.output)
        return self.structured_model


def _invoke(message: str, user_id: str = "USER-001") -> dict:
    return _graph().invoke(
        {
            "messages": [{"role": "user", "content": message}],
            "user_id": user_id,
            "thread_id": "THREAD-001",
            "tool_calls": [],
            "safety_flags": [],
            "agent_steps": [],
        }
    )


def test_multi_agent_debug_metadata_keeps_stable_trace_fields() -> None:
    debug = build_multi_agent_debug_metadata(
        {
            "supervisor_decision": {"routes": ["product_agent"]},
            "agent_steps": [{"node": "supervisor"}],
            "routes": ["product_agent"],
            "executed_routes": ["product_agent"],
            "decision": {"answer_type": "single_read_summary"},
            "safety_flags": [],
            "product_summary": {"raw_detail": "SHOULD_NOT_LEAK"},
        }
    )

    assert debug == {
        "supervisor_decision": {"routes": ["product_agent"]},
        "agent_steps": [{"node": "supervisor"}],
        "routes": ["product_agent"],
        "executed_routes": ["product_agent"],
        "decision": {"answer_type": "single_read_summary"},
        "safety_flags": [],
    }
    assert "SHOULD_NOT_LEAK" not in str(debug)


def test_product_search_question_routes_to_product_agent() -> None:
    result = _invoke("推荐一个键盘")

    assert result["supervisor_decision"]["intent"] == "read_path"
    assert result["routes"] == ["product_agent"]
    assert result["supervisor_decision"]["routes"] == ["product_agent"]
    assert result["supervisor_decision"]["routing_reasons"] == {
        "product_agent": "matched_product_keywords"
    }
    assert result["supervisor_decision"]["confidence"] == "high"
    assert result["supervisor_decision"]["fallback_used"] is False
    assert result["supervisor_decision"]["router_type"] == "deterministic"
    assert result["executed_routes"] == ["product_agent"]
    assert result["tool_calls"] == ["search_products"]
    assert result["product_summary"]["product_count"] == 1
    assert result["product_summary"]["product_ids"] == ["TECH-KEY-001"]
    assert result["product_summary"]["confidence"] == "high"
    assert result["product_summary"]["raw_result_stored"] is False
    assert "RAW_PRODUCT_DETAIL_SHOULD_NOT_LEAK" not in str(result["product_summary"])


def test_document_or_policy_question_routes_to_rag_agent() -> None:
    result = _invoke("退货政策是什么")

    assert result["routes"] == ["rag_agent"]
    assert result["executed_routes"] == ["rag_agent"]
    assert result["tool_calls"] == ["search_policy_docs"]
    assert result["rag_summary"]["source"] == "search_policy_docs"
    assert result["rag_summary"]["doc_type"] == "policy"
    assert result["rag_summary"]["raw_result_stored"] is False


def test_preference_question_routes_to_preference_agent() -> None:
    result = _invoke("我的偏好适合什么")

    assert result["routes"] == ["preference_agent"]
    assert result["executed_routes"] == ["preference_agent"]
    assert result["tool_calls"] == ["get_user_preferences"]
    assert result["preference_summary"]["user_id"] == "USER-001"
    assert result["preference_summary"]["preference_count"] == 1
    assert result["preference_summary"]["has_preferences"] is True
    assert result["preference_summary"]["raw_result_stored"] is False
    assert "RAW_PREFERENCE_SHOULD_NOT_LEAK" not in str(result["preference_summary"])


def test_mixed_question_runs_read_agents_in_order() -> None:
    result = _invoke("结合我的偏好推荐键盘，并看看退货政策")

    assert result["routes"] == ["product_agent", "rag_agent", "preference_agent"]
    assert result["executed_routes"] == [
        "product_agent",
        "rag_agent",
        "preference_agent",
    ]
    assert result["tool_calls"] == [
        "search_products",
        "search_policy_docs",
        "get_user_preferences",
    ]
    assert [step["node"] for step in result["agent_steps"]] == [
        "supervisor",
        "route_dispatcher",
        "product_agent",
        "route_dispatcher",
        "rag_agent",
        "route_dispatcher",
        "preference_agent",
        "route_dispatcher",
        "decision_agent",
    ]
    assert [step["index"] for step in result["agent_steps"]] == list(range(1, 10))
    assert result["agent_steps"][1]["selected_route"] == "product_agent"
    assert result["agent_steps"][3]["selected_route"] == "rag_agent"
    assert result["agent_steps"][5]["selected_route"] == "preference_agent"
    assert result["agent_steps"][7]["event"] == "selected_decision_agent"
    assert "RAW_PRODUCT_DETAIL_SHOULD_NOT_LEAK" not in str(result["agent_steps"])
    assert "RAW_PREFERENCE_SHOULD_NOT_LEAK" not in str(result["agent_steps"])
    assert result["agent_steps"][0]["confidence"] == "high"
    assert result["agent_steps"][0]["fallback_used"] is False
    assert result["agent_steps"][0]["router_type"] == "deterministic"


def test_decision_agent_runs_once_after_all_routes() -> None:
    result = _invoke("结合我的偏好推荐键盘，并看看退货政策")

    assert result["decision"]["used_routes"] == result["executed_routes"]
    assert result["decision"]["answer_type"] == "combined_read_summary"
    assert result["decision"]["used_summaries"] == [
        "product_summary",
        "rag_summary",
        "preference_summary",
    ]
    assert result["decision"]["requires_followup"] is False
    assert result["decision"]["followup_reason"] is None
    assert result["decision"]["tool_calls"] == result["tool_calls"]
    assert result["agent_steps"][-1]["node"] == "decision_agent"
    assert result["agent_steps"][-1]["answer_type"] == "combined_read_summary"
    assert result["final_response"].count("商品信息") == 1
    assert result["final_response"].count("文档/政策信息") == 1
    assert result["final_response"].count("用户偏好") == 1


def test_decision_agent_requires_followup_without_read_summaries() -> None:
    result = decision_agent_node(
        {
            "executed_routes": [],
            "tool_calls": [],
            "safety_flags": [],
        }
    )

    assert result["decision"]["answer_type"] == "insufficient_context"
    assert result["decision"]["used_summaries"] == []
    assert result["decision"]["requires_followup"] is True
    assert result["decision"]["followup_reason"] == "no_read_summary_available"
    assert result["final_response"] == "我目前没有检索到足够的信息，请补充商品、政策或偏好相关问题。"


def test_routes_do_not_include_decision_agent() -> None:
    routes = determine_routes("结合我的偏好推荐键盘，并看看退货政策", user_id="USER-001")

    assert "decision_agent" not in routes


def test_supervisor_decision_records_fallback_and_missing_user_id() -> None:
    fallback_decision = build_supervisor_decision("随便看看")

    assert fallback_decision["routes"] == ["product_agent"]
    assert fallback_decision["routing_reasons"] == {
        "product_agent": "fallback_to_product_read"
    }
    assert fallback_decision["confidence"] == "medium"
    assert fallback_decision["fallback_used"] is True

    preference_without_user = build_supervisor_decision("我的偏好适合什么")

    assert preference_without_user["routes"] == ["product_agent"]
    assert preference_without_user["requires_user_id_for_preferences"] is True


def test_write_intent_bypasses_read_agents_and_requires_handoff() -> None:
    result = _invoke("Please add to cart TECH-KEY-001")

    assert result["supervisor_decision"]["intent"] == "write_path_unsupported"
    assert result["supervisor_decision"]["routes"] == []
    assert result["supervisor_decision"]["confidence"] == "high"
    assert result["supervisor_decision"]["fallback_used"] is False
    assert result["supervisor_decision"]["router_type"] == "deterministic"
    assert result["supervisor_decision"]["safety_flags"] == ["write_intent_blocked"]
    assert (
        result["supervisor_decision"]["handoff_reason"]
        == "read_only_multi_agent_write_intent"
    )
    assert result["routes"] == []
    assert result["executed_routes"] == []
    assert result["tool_calls"] == []
    assert result["safety_flags"] == ["write_intent_blocked"]
    assert result["decision"]["status"] == "handoff_required"
    assert result["decision"]["answer_type"] == "write_path_handoff"
    assert result["decision"]["used_summaries"] == []
    assert result["decision"]["requires_followup"] is True
    assert (
        result["decision"]["followup_reason"]
        == "read_only_multi_agent_write_intent"
    )
    assert [step["node"] for step in result["agent_steps"]] == [
        "supervisor",
        "route_dispatcher",
        "decision_agent",
    ]
    assert result["agent_steps"][1]["event"] == "selected_decision_agent"
    assert result["agent_steps"][2]["event"] == "handoff_required"
    assert "V3" in result["final_response"]


def test_graph_can_use_injected_supervisor_router() -> None:
    product_tools = tools_by_name([guard_tool("product_agent", fake_search_products)])
    rag_tools = tools_by_name(
        [
            guard_tool("rag_agent", fake_search_product_docs),
            guard_tool("rag_agent", fake_search_policy_docs),
        ]
    )
    graph = create_shopmind_multi_agent_graph(
        product_tools=product_tools,
        rag_tools=rag_tools,
        preference_tools={},
        supervisor_router=RagOnlyTestRouter(),
    )

    result = graph.invoke(
        {
            "messages": [{"role": "user", "content": "推荐一个键盘"}],
            "user_id": "USER-001",
            "thread_id": "THREAD-001",
            "tool_calls": [],
            "safety_flags": [],
            "agent_steps": [],
        }
    )

    assert result["routes"] == ["rag_agent"]
    assert result["executed_routes"] == ["rag_agent"]
    assert result["supervisor_decision"]["router_type"] == "test"
    assert result["supervisor_decision"]["routing_reasons"] == {
        "rag_agent": "test_router_forced_rag"
    }
    assert result["tool_calls"] == ["search_product_docs"]
    assert result["agent_steps"][0]["router_type"] == "test"


def test_llm_supervisor_router_uses_structured_provider() -> None:
    def provider(payload: LLMSupervisorRouterInput) -> LLMSupervisorRouterOutput:
        assert payload["message"] == "推荐键盘并看看退货政策"
        assert payload["user_id"] == "USER-001"
        assert payload["allowed_routes"] == [
            "preference_agent",
            "product_agent",
            "rag_agent",
        ]
        return {
            "routes": ["product_agent", "rag_agent"],
            "routing_reasons": {
                "product_agent": "llm_detected_product_need",
                "rag_agent": "llm_detected_policy_need",
            },
            "confidence": "high",
            "requires_user_id_for_preferences": False,
        }

    decision = build_supervisor_decision(
        "推荐键盘并看看退货政策",
        user_id="USER-001",
        router=LLMSupervisorRouter(decision_provider=provider),
    )

    assert decision["routes"] == ["product_agent", "rag_agent"]
    assert decision["routing_reasons"] == {
        "product_agent": "llm_detected_product_need",
        "rag_agent": "llm_detected_policy_need",
    }
    assert decision["confidence"] == "high"
    assert decision["fallback_used"] is False
    assert decision["router_type"] == "llm"


def test_llm_supervisor_router_normalizes_invalid_confidence() -> None:
    def provider(payload: LLMSupervisorRouterInput) -> dict:
        assert payload["allowed_routes"] == [
            "preference_agent",
            "product_agent",
            "rag_agent",
        ]
        return {
            "routes": ["rag_agent"],
            "confidence": "certain",
        }

    decision = build_supervisor_decision(
        "看看退货政策",
        router=LLMSupervisorRouter(decision_provider=provider),
    )

    assert decision["routes"] == ["rag_agent"]
    assert decision["routing_reasons"] == {"rag_agent": "llm_selected_route"}
    assert decision["confidence"] == "medium"
    assert decision["router_type"] == "llm"


def test_langchain_supervisor_provider_uses_structured_output_contract() -> None:
    fake_model = FakeChatModel(
        {
            "routes": ["preference_agent"],
            "routing_reasons": {
                "preference_agent": "structured_model_detected_preferences"
            },
            "confidence": "high",
            "requires_user_id_for_preferences": False,
        }
    )
    provider = create_langchain_supervisor_decision_provider(model=fake_model)

    decision = build_supervisor_decision(
        "我的偏好适合什么",
        user_id="USER-001",
        router=LLMSupervisorRouter(decision_provider=provider),
    )

    assert fake_model.schema is LLMSupervisorRouterOutput
    assert fake_model.structured_model is not None
    messages = fake_model.structured_model.messages
    assert messages is not None
    assert messages[0]["role"] == "system"
    assert "decision_agent" in messages[0]["content"]
    assert "Allowed routes: preference_agent, product_agent, rag_agent" in messages[1][
        "content"
    ]
    assert decision["routes"] == ["preference_agent"]
    assert decision["routing_reasons"] == {
        "preference_agent": "structured_model_detected_preferences"
    }
    assert decision["router_type"] == "llm"


def test_llm_supervisor_router_falls_back_on_invalid_routes() -> None:
    router = LLMSupervisorRouter(
        decision_provider=lambda payload: {
            "routes": ["decision_agent"],
            "confidence": "high",
        },
        provider_type="custom_callable",
        model_name="test-router",
    )

    decision = build_supervisor_decision("推荐一个键盘", user_id="USER-001", router=router)

    assert decision["routes"] == ["product_agent"]
    assert decision["router_type"] == "llm_fallback"
    assert decision["fallback_reason"] == "invalid_routes"
    assert decision["fallback_router_type"] == "deterministic"
    assert decision["router_provider"] == "custom_callable"
    assert decision["router_model"] == "test-router"
    assert decision["fallback_used"] is False


def test_llm_supervisor_router_falls_back_when_unconfigured() -> None:
    decision = build_supervisor_decision(
        "我的偏好适合什么",
        user_id="USER-001",
        router=LLMSupervisorRouter(),
    )

    assert decision["routes"] == ["preference_agent"]
    assert decision["router_type"] == "llm_fallback"
    assert decision["fallback_reason"] == "provider_not_configured"


def test_llm_supervisor_router_blocks_write_intent_before_provider() -> None:
    def provider(payload: LLMSupervisorRouterInput) -> LLMSupervisorRouterOutput:
        raise AssertionError("provider should not be called for write intent")

    decision = build_supervisor_decision(
        "Please add to cart TECH-KEY-001",
        user_id="USER-001",
        router=LLMSupervisorRouter(
            decision_provider=provider,
            provider_type="custom_callable",
            model_name="test-router",
        ),
    )

    assert decision["intent"] == "write_path_unsupported"
    assert decision["routes"] == []
    assert decision["router_type"] == "llm_guardrail"
    assert decision["router_provider"] == "custom_callable"
    assert decision["router_model"] == "test-router"
    assert decision["safety_flags"] == ["write_intent_blocked"]
    assert decision["handoff_reason"] == "read_only_multi_agent_write_intent"


def test_create_supervisor_router_from_config_mode() -> None:
    deterministic = create_supervisor_router("deterministic")
    llm = create_supervisor_router(
        "llm",
        decision_provider=lambda payload: {
            "routes": ["product_agent"],
            "confidence": "high",
        },
    )
    invalid = create_supervisor_router("unknown")

    assert deterministic.route("推荐键盘")["router_type"] == "deterministic"
    assert llm.route("推荐键盘")["router_type"] == "llm"
    assert invalid.route("推荐键盘")["router_type"] == "deterministic"


def test_create_supervisor_router_records_langchain_metadata() -> None:
    fake_model = FakeChatModel(
        {
            "routes": ["rag_agent"],
            "confidence": "high",
        }
    )
    llm = create_supervisor_router("llm", model=fake_model)

    decision = llm.route("看看退货政策", user_id="USER-001")

    assert decision["router_type"] == "llm"
    assert decision["router_provider"] == "langchain_structured_output"
    assert decision["router_model"] == "FakeChatModel"


def test_graph_records_llm_router_observability_metadata() -> None:
    product_tools = tools_by_name([guard_tool("product_agent", fake_search_products)])
    graph = create_shopmind_multi_agent_graph(
        product_tools=product_tools,
        rag_tools={},
        preference_tools={},
        supervisor_router=LLMSupervisorRouter(
            decision_provider=lambda payload: {
                "routes": ["decision_agent"],
                "confidence": "high",
            },
            provider_type="custom_callable",
            model_name="test-router",
        ),
    )

    result = graph.invoke(
        {
            "messages": [{"role": "user", "content": "推荐一个键盘"}],
            "user_id": "USER-001",
            "thread_id": "THREAD-001",
            "tool_calls": [],
            "safety_flags": [],
            "agent_steps": [],
        }
    )

    supervisor_step = result["agent_steps"][0]
    assert result["supervisor_decision"]["router_type"] == "llm_fallback"
    assert supervisor_step["router_type"] == "llm_fallback"
    assert supervisor_step["router_provider"] == "custom_callable"
    assert supervisor_step["router_model"] == "test-router"
    assert supervisor_step["fallback_reason"] == "invalid_routes"
    assert supervisor_step["fallback_router_type"] == "deterministic"
