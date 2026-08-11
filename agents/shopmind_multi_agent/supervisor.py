"""Supervisor node for V3 read-only routing."""

from typing import Any

from .planning import AgentPlanner, DeterministicAgentPlanner
from .observability import append_agent_step
from .state import ShopMindMultiAgentState
from .supervisor_router import DeterministicSupervisorRouter, SupervisorRouter


SUPERVISOR_TOOLS: list[Any] = []
DEFAULT_SUPERVISOR_ROUTER = DeterministicSupervisorRouter()
DEFAULT_AGENT_PLANNER = DeterministicAgentPlanner()


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
    planner: AgentPlanner | None = None,
    runtime_context: Any | None = None,
) -> dict[str, Any]:
    message = get_last_user_message(state)
    user_id = state.get("user_id")
    supervisor_decision = build_supervisor_decision(
        message,
        user_id=user_id,
        router=router,
    )
    routes = list(supervisor_decision["routes"])
    policy_metadata = getattr(
        getattr(runtime_context, "policy", None),
        "metadata",
        {},
    )
    execution_plan = (planner or DEFAULT_AGENT_PLANNER).build_plan(
        routes,
        message=message,
        routing_reasons=supervisor_decision.get("routing_reasons"),
        run_id=getattr(runtime_context, "run_id", None),
        parallel_enabled=bool(policy_metadata.get("parallel_read_enabled", False)),
        max_parallelism=int(policy_metadata.get("parallel_read_max_workers", 1)),
        retry_policy=getattr(
            getattr(runtime_context, "policy", None),
            "agent_task_retry_policy",
            None,
        ),
    )
    safety_flags = list(state.get("safety_flags", []))
    for flag in supervisor_decision.get("safety_flags", []):
        if flag not in safety_flags:
            safety_flags.append(flag)

    return {
        "intent": supervisor_decision["intent"],
        "supervisor_decision": supervisor_decision,
        # Graph state is persisted in JSONB; use the JSON representation so
        # retry-policy frozensets and other typed containers cannot leak into
        # the runtime result and make a successful recommendation unpersistable.
        "execution_plan": execution_plan.model_dump(mode="json"),
        "routes": routes,
        "executed_routes": [],
        "current_route": None,
        "handoff_reason": supervisor_decision.get("handoff_reason"),
        "safety_flags": safety_flags,
        "tool_calls": list(state.get("tool_calls", [])),
        "agent_steps": append_agent_step(
            state,
            node="supervisor",
            event="routed",
            routes=routes,
            plan_id=execution_plan.plan_id,
            plan_step_count=len(execution_plan.steps),
            plan_execution_mode=execution_plan.execution_mode,
            plan_max_parallelism=execution_plan.max_parallelism,
            planner_type=execution_plan.planner_type,
            planner_provider=execution_plan.metadata.get("planner_provider"),
            planner_model=execution_plan.metadata.get("planner_model"),
            planner_fallback_reason=execution_plan.metadata.get(
                "planner_fallback_reason"
            ),
            fallback_planner_type=execution_plan.metadata.get(
                "fallback_planner_type"
            ),
            intent=supervisor_decision["intent"],
            confidence=supervisor_decision["confidence"],
            fallback_used=supervisor_decision["fallback_used"],
            router_type=supervisor_decision.get("router_type"),
            router_provider=supervisor_decision.get("router_provider"),
            router_model=supervisor_decision.get("router_model"),
            fallback_reason=supervisor_decision.get("fallback_reason"),
            fallback_router_type=supervisor_decision.get("fallback_router_type"),
            handoff_reason=supervisor_decision.get("handoff_reason"),
            safety_flags=supervisor_decision.get("safety_flags", []),
        ),
    }
