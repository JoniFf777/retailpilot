"""LangGraph orchestration for the ShopMind V3 read-only multi-agent path."""

from typing import Any, Callable

from langgraph.graph import END, START, StateGraph

from app.runtime import (
    AgentAdapter,
    AgentAdapterError,
    AgentAdapterRegistry,
    AgentExecutionPlan,
    AgentPlanAttemptEvent,
    AgentPlanExecutionMode,
    AgentPlanStep,
    AgentPlanStepResult,
    AgentResult,
    AgentTaskStatus,
    AgentTaskRetryOwner,
    BoundedPlanExecutor,
    DelegationBudgetGuard,
    EventVisibility,
    HttpAgentAdapter,
    MemoryReference,
    PolicyEnforcedAgentAdapter,
    RunUsage,
)
from app.core.settings import Settings, get_settings

from .decision_agent import decision_agent_node
from .observability import append_agent_step
from .parallel_state import build_isolated_step_state, merge_parallel_step_results
from .permissions import guard_tools
from .planning import AgentPlanner
from .product_agent import PRODUCT_AGENT_TOOLS
from .product_adapter import create_product_agent_adapter, product_agent_adapter_node
from .preference_adapter import (
    create_preference_agent_adapter,
    preference_agent_adapter_node,
)
from .rag_adapter import create_rag_agent_adapter, rag_agent_adapter_node
from .rag_agent import RAG_AGENT_TOOLS
from .state import ShopMindMultiAgentState
from .preference_agent import PREFERENCE_AGENT_TOOLS
from .supervisor import supervisor_node
from .supervisor_router import SupervisorRouter


READ_AGENT_ROUTES = ("product_agent", "rag_agent", "preference_agent")
DEBUG_METADATA_KEYS = (
    "supervisor_decision",
    "execution_plan",
    "parallel_execution",
    "agent_steps",
    "routes",
    "executed_routes",
    "decision",
    "safety_flags",
)


def build_multi_agent_debug_metadata(raw_result: dict[str, Any]) -> dict[str, Any]:
    """Return stable, non-raw metadata for API debug/evaluation consumers."""
    return {
        key: raw_result[key]
        for key in DEBUG_METADATA_KEYS
        if raw_result.get(key) is not None
    }


def route_dispatcher_node(state: ShopMindMultiAgentState) -> dict[str, Any]:
    routes = list(state.get("routes", []))
    executed_routes = list(state.get("executed_routes", []))
    plan = AgentExecutionPlan.model_validate(state.get("execution_plan") or {})

    for route in routes:
        if route not in executed_routes:
            plan_step_id = next(
                (
                    step.step_id
                    for step in plan.steps
                    if step.recipient == route
                ),
                None,
            )
            return {
                "current_route": route,
                "plan_step_id": plan_step_id,
                "agent_steps": append_agent_step(
                    state,
                    node="route_dispatcher",
                    event="selected_route",
                    selected_route=route,
                    executed_routes=executed_routes,
                ),
            }

    return {
        "current_route": None,
        "plan_step_id": None,
        "agent_steps": append_agent_step(
            state,
            node="route_dispatcher",
            event="selected_decision_agent",
            executed_routes=executed_routes,
        ),
    }


def next_route(state: ShopMindMultiAgentState) -> str:
    return state.get("current_route") or "decision_agent"


def next_execution_path(state: ShopMindMultiAgentState) -> str:
    plan = AgentExecutionPlan.model_validate(state.get("execution_plan") or {})
    if plan.execution_mode == AgentPlanExecutionMode.BOUNDED_PARALLEL or any(
        step.retry_policy.owner == AgentTaskRetryOwner.PLAN_EXECUTOR
        for step in plan.steps
    ):
        return "parallel_read_executor"
    return "route_dispatcher"


def parallel_read_executor_node(
    state: ShopMindMultiAgentState,
    *,
    specialist_nodes: dict[str, Callable[[ShopMindMultiAgentState], dict[str, Any]]],
    runtime_context: Any | None = None,
) -> dict[str, Any]:
    """Execute policy-owned read plans with isolated graph state."""

    plan = AgentExecutionPlan.model_validate(state.get("execution_plan") or {})
    executor = BoundedPlanExecutor(parallel_enabled=True)

    def handler(step: AgentPlanStep) -> AgentResult:
        isolated_state = build_isolated_step_state(state, step)
        output = specialist_nodes[step.recipient](isolated_state)
        references = [
            reference
            if isinstance(reference, MemoryReference)
            else MemoryReference.model_validate(reference)
            for reference in output.get("evidence_references", [])
        ]
        delegated_usage = output.get("delegated_usage", [])
        usage = (
            RunUsage.model_validate(delegated_usage[-1])
            if isinstance(delegated_usage, list) and delegated_usage
            else RunUsage()
        )
        return AgentResult(
            task_id=step.step_id,
            status=AgentTaskStatus.COMPLETED,
            output_data=output,
            evidence_references=references,
            usage=usage,
            metadata={"graph_node": step.recipient, "plan_step_id": step.step_id},
        )

    def emit_event(
        event_type: str,
        *,
        payload: dict[str, Any],
        agent_name: str | None = None,
    ) -> None:
        if runtime_context is not None:
            runtime_context.emit_event(
                event_type,
                visibility=EventVisibility.INTERNAL,
                payload=payload,
                agent_name=agent_name,
            )

    def observe_step(
        lifecycle: str,
        step: AgentPlanStep,
        result: AgentPlanStepResult | None,
    ) -> None:
        payload: dict[str, Any] = {
            "plan_id": plan.plan_id,
            "step_id": step.step_id,
            "recipient": step.recipient,
        }
        if result is not None:
            payload["status"] = result.status
            payload["attempt_count"] = result.attempt_count
            if result.error is not None:
                payload["error_code"] = result.error.code
        emit_event(
            f"plan.step.{lifecycle}",
            payload=payload,
            agent_name=step.recipient,
        )

    def observe_attempt(event: AgentPlanAttemptEvent) -> None:
        payload = event.model_dump(mode="json", exclude_none=True)
        payload["plan_id"] = plan.plan_id
        emit_event(
            f"plan.step.{event.lifecycle}",
            payload=payload,
            agent_name=event.recipient,
        )

    emit_event(
        "plan.execution.started",
        payload={
            "plan_id": plan.plan_id,
            "execution_mode": plan.execution_mode,
            "step_count": len(plan.steps),
            "max_parallelism": plan.max_parallelism,
        },
    )
    plan_result = executor.execute(
        plan,
        handler,
        cancellation_check=(
            None
            if runtime_context is None
            else runtime_context.refresh_cancellation
        ),
        step_observer=observe_step,
        attempt_observer=observe_attempt,
    )
    emit_event(
        "plan.execution.completed",
        payload={
            "plan_id": plan.plan_id,
            "status": plan_result.status,
            "completed_step_count": sum(
                step.status == "completed" for step in plan_result.step_results
            ),
            "cancelled_step_count": sum(
                step.status == "cancelled" for step in plan_result.step_results
            ),
            "failed_step_count": sum(
                step.status == "failed" for step in plan_result.step_results
            ),
        },
    )
    return merge_parallel_step_results(state, plan, plan_result)


def _bind_product_adapter(
    adapter: AgentAdapter,
    runtime_context: Any | None,
) -> Callable[[ShopMindMultiAgentState], dict[str, Any]]:
    return lambda state: product_agent_adapter_node(
        state,
        adapter=adapter,
        runtime_context=runtime_context,
    )


def _bind_rag_adapter(
    adapter: AgentAdapter,
    runtime_context: Any | None,
) -> Callable[[ShopMindMultiAgentState], dict[str, Any]]:
    return lambda state: rag_agent_adapter_node(
        state,
        adapter=adapter,
        runtime_context=runtime_context,
    )


def _bind_preference_adapter(
    adapter: AgentAdapter,
    runtime_context: Any | None,
) -> Callable[[ShopMindMultiAgentState], dict[str, Any]]:
    return lambda state: preference_agent_adapter_node(
        state,
        adapter=adapter,
        runtime_context=runtime_context,
    )


def create_shopmind_agent_adapter_registry(
    *,
    product_tools: Any | None,
    rag_tools: Any | None,
    preference_tools: Any | None,
    delegation_guard: DelegationBudgetGuard,
    settings: Settings | None = None,
    rag_http_client: Any | None = None,
) -> AgentAdapterRegistry:
    """Build the server-owned registry with an optional remote RAG transport."""

    runtime_settings = settings or get_settings()
    rag_adapter: AgentAdapter
    if runtime_settings.shopmind_rag_agent_transport == "http":
        endpoint = runtime_settings.shopmind_rag_agent_http_endpoint
        allowed_hosts = runtime_settings.shopmind_rag_agent_http_allowed_hosts
        if endpoint is None or not allowed_hosts:
            raise AgentAdapterError(
                "Remote RAG Agent transport configuration is incomplete."
            )
        secret = runtime_settings.shopmind_rag_agent_http_bearer_token
        rag_adapter = PolicyEnforcedAgentAdapter(
            adapter=HttpAgentAdapter(
                agent_name="rag_agent",
                endpoint_url=endpoint,
                allowed_https_hosts=allowed_hosts,
                timeout_seconds=(
                    runtime_settings.shopmind_rag_agent_http_timeout_seconds
                ),
                max_response_bytes=(
                    runtime_settings.shopmind_rag_agent_http_max_response_bytes
                ),
                authorization_bearer_token=(
                    secret.get_secret_value() if secret is not None else None
                ),
                client=rag_http_client,
            ),
            delegation_guard=delegation_guard,
        )
    else:
        rag_adapter = create_rag_agent_adapter(rag_tools, delegation_guard)

    return AgentAdapterRegistry(
        [
            create_product_agent_adapter(product_tools, delegation_guard),
            rag_adapter,
            create_preference_agent_adapter(preference_tools, delegation_guard),
        ],
        require_policy=True,
    )


def _bind_supervisor_node(
    router: SupervisorRouter | None,
    planner: AgentPlanner | None,
    runtime_context: Any | None,
) -> Callable[[ShopMindMultiAgentState], dict[str, Any]]:
    return lambda state: supervisor_node(
        state,
        router=router,
        planner=planner,
        runtime_context=runtime_context,
    )


def create_shopmind_multi_agent_graph(
    product_tools: Any | None = None,
    rag_tools: Any | None = None,
    preference_tools: Any | None = None,
    supervisor_router: SupervisorRouter | None = None,
    agent_planner: AgentPlanner | None = None,
    runtime_context: Any | None = None,
    adapter_settings: Settings | None = None,
    rag_http_client: Any | None = None,
):
    if runtime_context is not None:
        product_tools = product_tools or guard_tools(
            "product_agent",
            PRODUCT_AGENT_TOOLS,
            runtime_context=runtime_context,
        )
        rag_tools = rag_tools or guard_tools(
            "rag_agent",
            RAG_AGENT_TOOLS,
            runtime_context=runtime_context,
        )
        preference_tools = preference_tools or guard_tools(
            "preference_agent",
            PREFERENCE_AGENT_TOOLS,
            runtime_context=runtime_context,
        )

    graph = StateGraph(ShopMindMultiAgentState)
    delegation_guard = DelegationBudgetGuard(
        trusted_budget=getattr(runtime_context, "budget", None),
        trusted_deadline_at=getattr(
            getattr(runtime_context, "request", None),
            "deadline_at",
            None,
        ),
        run_started_at=getattr(runtime_context, "started_at", None),
    )
    adapter_registry = create_shopmind_agent_adapter_registry(
        product_tools=product_tools,
        rag_tools=rag_tools,
        preference_tools=preference_tools,
        delegation_guard=delegation_guard,
        settings=adapter_settings,
        rag_http_client=rag_http_client,
    )
    product_node = _bind_product_adapter(
        adapter_registry.resolve("product_agent"),
        runtime_context,
    )
    rag_node = _bind_rag_adapter(
        adapter_registry.resolve("rag_agent"),
        runtime_context,
    )
    preference_node = _bind_preference_adapter(
        adapter_registry.resolve("preference_agent"),
        runtime_context,
    )
    specialist_nodes = {
        "product_agent": product_node,
        "rag_agent": rag_node,
        "preference_agent": preference_node,
    }

    graph.add_node(
        "supervisor",
        _bind_supervisor_node(supervisor_router, agent_planner, runtime_context),
    )
    graph.add_node("route_dispatcher", route_dispatcher_node)
    graph.add_node("product_agent", product_node)
    graph.add_node("rag_agent", rag_node)
    graph.add_node("preference_agent", preference_node)
    graph.add_node(
        "parallel_read_executor",
        lambda state: parallel_read_executor_node(
            state,
            specialist_nodes=specialist_nodes,
            runtime_context=runtime_context,
        ),
    )
    graph.add_node("decision_agent", decision_agent_node)

    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges(
        "supervisor",
        next_execution_path,
        {
            "route_dispatcher": "route_dispatcher",
            "parallel_read_executor": "parallel_read_executor",
        },
    )
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
    graph.add_edge("parallel_read_executor", "decision_agent")
    graph.add_edge("decision_agent", END)

    return graph.compile()


def invoke_shopmind_multi_agent(
    message: str,
    user_id: str | None = None,
    thread_id: str | None = None,
    supervisor_router: SupervisorRouter | None = None,
    agent_planner: AgentPlanner | None = None,
    runtime_context: Any | None = None,
) -> dict[str, Any]:
    graph = create_shopmind_multi_agent_graph(
        supervisor_router=supervisor_router,
        agent_planner=agent_planner,
        runtime_context=runtime_context,
    )
    raw_result = graph.invoke(
        {
            "messages": [{"role": "user", "content": message}],
            "user_id": user_id or "",
            "thread_id": thread_id,
            "safety_flags": [],
            "tool_calls": [],
            "agent_steps": [],
            "delegated_usage": [],
        }
    )

    return {
        "answer": raw_result.get("final_response", ""),
        "status": "completed",
        "tool_calls": raw_result.get("tool_calls", []),
        "delegated_usage": raw_result.get("delegated_usage", []),
        "tool_call_records": (
            []
            if runtime_context is None
            else runtime_context.metadata_snapshot().get("tool_call_records", [])
        ),
        "debug": build_multi_agent_debug_metadata(raw_result),
        "raw_result": raw_result,
    }
