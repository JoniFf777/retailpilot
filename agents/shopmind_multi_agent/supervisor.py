"""Supervisor node for V3 read-only routing."""

from typing import Any

from .observability import append_agent_step
from .state import ShopMindMultiAgentState
from .supervisor_router import DeterministicSupervisorRouter, SupervisorRouter


SUPERVISOR_TOOLS: list[Any] = []
DEFAULT_SUPERVISOR_ROUTER = DeterministicSupervisorRouter()


def get_last_user_message(state: ShopMindMultiAgentState) -> str:
    messages = state.get("messages", [])
    if not messages:
        return ""

    last_message = messages[-1]
    if isinstance(last_message, dict):
        return str(last_message.get("content") or "")
    return str(getattr(last_message, "content", last_message))


def build_supervisor_decision(
    message: str,
    user_id: str | None = None,
    router: SupervisorRouter | None = None,
) -> dict[str, Any]:
    return (router or DEFAULT_SUPERVISOR_ROUTER).route(message, user_id=user_id)


def determine_routes(
    message: str,
    user_id: str | None = None,
    router: SupervisorRouter | None = None,
) -> list[str]:
    return list(
        build_supervisor_decision(message, user_id=user_id, router=router)["routes"]
    )


def supervisor_node(
    state: ShopMindMultiAgentState,
    router: SupervisorRouter | None = None,
) -> dict[str, Any]:
    message = get_last_user_message(state)
    user_id = state.get("user_id")
    supervisor_decision = build_supervisor_decision(
        message,
        user_id=user_id,
        router=router,
    )
    routes = list(supervisor_decision["routes"])

    return {
        "intent": supervisor_decision["intent"],
        "supervisor_decision": supervisor_decision,
        "routes": routes,
        "executed_routes": [],
        "current_route": None,
        "safety_flags": list(state.get("safety_flags", [])),
        "tool_calls": list(state.get("tool_calls", [])),
        "agent_steps": append_agent_step(
            state,
            node="supervisor",
            event="routed",
            routes=routes,
            intent=supervisor_decision["intent"],
            confidence=supervisor_decision["confidence"],
            fallback_used=supervisor_decision["fallback_used"],
            router_type=supervisor_decision.get("router_type"),
        ),
    }
