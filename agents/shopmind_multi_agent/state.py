"""State schema for the ShopMind V3 read-only multi-agent path."""

from typing import Any, Optional, TypedDict


class ShopMindMultiAgentState(TypedDict, total=False):
    messages: list[Any]
    user_id: str
    thread_id: Optional[str]

    intent: Optional[str]
    supervisor_decision: Optional[dict[str, Any]]
    routes: list[str]
    executed_routes: list[str]
    current_route: Optional[str]

    product_summary: Optional[dict[str, Any]]
    rag_summary: Optional[dict[str, Any]]
    preference_summary: Optional[dict[str, Any]]

    decision: Optional[dict[str, Any]]
    final_response: Optional[str]
    safety_flags: list[str]
    tool_calls: list[str]
    agent_steps: list[dict[str, Any]]
