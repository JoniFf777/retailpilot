from langchain_core.tools import tool

from agents.shopmind_multi_agent import create_shopmind_multi_agent_graph
from agents.shopmind_multi_agent.permissions import guard_tool, tools_by_name
from agents.shopmind_multi_agent.supervisor import determine_routes


@tool("search_products")
def fake_search_products(query: str, limit: int = 5) -> str:
    """Fake product search."""
    return "找到 1 个符合条件的商品：测试键盘（TECH-KEY-001）"


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
    return f"用户 {user_id} 偏好：安静键盘。"


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


def _invoke(message: str, user_id: str = "USER-001") -> dict:
    return _graph().invoke(
        {
            "messages": [{"role": "user", "content": message}],
            "user_id": user_id,
            "thread_id": "THREAD-001",
            "tool_calls": [],
            "safety_flags": [],
        }
    )


def test_product_search_question_routes_to_product_agent() -> None:
    result = _invoke("推荐一个键盘")

    assert result["routes"] == ["product_agent"]
    assert result["executed_routes"] == ["product_agent"]
    assert result["tool_calls"] == ["search_products"]


def test_document_or_policy_question_routes_to_rag_agent() -> None:
    result = _invoke("退货政策是什么")

    assert result["routes"] == ["rag_agent"]
    assert result["executed_routes"] == ["rag_agent"]
    assert result["tool_calls"] == ["search_policy_docs"]


def test_preference_question_routes_to_preference_agent() -> None:
    result = _invoke("我的偏好适合什么")

    assert result["routes"] == ["preference_agent"]
    assert result["executed_routes"] == ["preference_agent"]
    assert result["tool_calls"] == ["get_user_preferences"]


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


def test_decision_agent_runs_once_after_all_routes() -> None:
    result = _invoke("结合我的偏好推荐键盘，并看看退货政策")

    assert result["decision"]["used_routes"] == result["executed_routes"]
    assert result["final_response"].count("商品信息") == 1
    assert result["final_response"].count("文档/政策信息") == 1
    assert result["final_response"].count("用户偏好") == 1


def test_routes_do_not_include_decision_agent() -> None:
    routes = determine_routes("结合我的偏好推荐键盘，并看看退货政策", user_id="USER-001")

    assert "decision_agent" not in routes
