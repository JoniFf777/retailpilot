"""LangGraph orchestration for the ShopMind V3 read-only multi-agent path."""

from typing import Any, Callable

from langgraph.graph import END, START, StateGraph

from .decision_agent import decision_agent_node
from .product_agent import product_agent_node
from .rag_agent import rag_agent_node
from .state import ShopMindMultiAgentState
from .preference_agent import preference_agent_node
from .supervisor import supervisor_node


READ_AGENT_ROUTES = ("product_agent", "rag_agent", "preference_agent")


def route_dispatcher_node(state: ShopMindMultiAgentState) -> dict[str, Any]:
    routes = list(state.get("routes", []))
    executed_routes = list(state.get("executed_routes", []))

    for route in routes:
        if route not in executed_routes:
            return {"current_route": route}

    return {"current_route": None}


def next_route(state: ShopMindMultiAgentState) -> str:
    return state.get("current_route") or "decision_agent"


def _bind_node(
    node: Callable[[ShopMindMultiAgentState, Any], dict[str, Any]],
    tools: Any,
) -> Callable[[ShopMindMultiAgentState], dict[str, Any]]:
    return lambda state: node(state, tools=tools)


def create_shopmind_multi_agent_graph(
    product_tools: Any | None = None,
    rag_tools: Any | None = None,
    preference_tools: Any | None = None,
):
    graph = StateGraph(ShopMindMultiAgentState)

    graph.add_node("supervisor", supervisor_node)
    graph.add_node("route_dispatcher", route_dispatcher_node)
    graph.add_node("product_agent", _bind_node(product_agent_node, product_tools))
    graph.add_node("rag_agent", _bind_node(rag_agent_node, rag_tools))
    graph.add_node("preference_agent", _bind_node(preference_agent_node, preference_tools))
    graph.add_node("decision_agent", decision_agent_node)

    graph.add_edge(START, "supervisor")
    graph.add_edge("supervisor", "route_dispatcher")
    graph.add_conditional_edges(
        "route_dispatcher",
        next_route,
        {
            "product_agent": "product_agent",
            "rag_agent": "rag_agent",
            "preference_agent": "preference_agent",
            "decision_agent": "decision_agent",
        },
    )
    for route in READ_AGENT_ROUTES:
        graph.add_edge(route, "route_dispatcher")
    graph.add_edge("decision_agent", END)

    return graph.compile()


def invoke_shopmind_multi_agent(
    message: str,
    user_id: str | None = None,
    thread_id: str | None = None,
) -> dict[str, Any]:
    graph = create_shopmind_multi_agent_graph()
    raw_result = graph.invoke(
        {
            "messages": [{"role": "user", "content": message}],
            "user_id": user_id or "",
            "thread_id": thread_id,
            "safety_flags": [],
            "tool_calls": [],
        }
    )

    return {
        "answer": raw_result.get("final_response", ""),
        "status": "completed",
        "tool_calls": raw_result.get("tool_calls", []),
        "raw_result": raw_result,
    }
