"""Deterministic read-task planning for the V5 collaboration boundary."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Protocol, TypedDict
from uuid import NAMESPACE_URL, uuid5

from langchain.chat_models import init_chat_model

from app.runtime import (
    AgentExecutionPlan,
    AgentPlanExecutionMode,
    AgentPlanStep,
    AgentTaskRetryPolicy,
)
from config import DEFAULT_MODEL


ROUTE_INTENTS = {
    "product_agent": "product_read",
    "rag_agent": "document_retrieval",
    "preference_agent": "preference_read",
}
PLANNER_SYSTEM_PROMPT = """You review a server-compiled ShopMind read plan.

Return one structured AgentExecutionPlan proposal. Do not add, remove, reorder,
or rename routes or steps. Do not change run identity, intents, dependencies,
execution mode, max parallelism, or retry policy. Do not add tools or write
capabilities.
When no policy-compliant change is possible, reproduce the baseline plan."""


class PlannerProviderInput(TypedDict):
    """Server-owned planning context passed to an optional structured provider."""

    message: str
    routes: list[str]
    routing_reasons: dict[str, str]
    baseline_plan: dict[str, Any]


PlanProvider = Callable[
    [PlannerProviderInput],
    AgentExecutionPlan | Mapping[str, Any],
]


def _coerce_plan_provider_output(
    output: object,
) -> AgentExecutionPlan | Mapping[str, Any]:
    if isinstance(output, AgentExecutionPlan):
        return output
    if hasattr(output, "model_dump"):
        return output.model_dump(exclude_none=True)
    if isinstance(output, Mapping):
        return output
    return {}


def _describe_planner_model(model: Any | None) -> str:
    configured_model = model or DEFAULT_MODEL
    if isinstance(configured_model, str):
        return configured_model
    return configured_model.__class__.__name__


def _build_langchain_planner_messages(
    payload: PlannerProviderInput,
) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Message: {payload['message']}\n"
                f"Supervisor routes: {', '.join(payload['routes'])}\n"
                "Canonical baseline plan:\n"
                f"{json.dumps(payload['baseline_plan'], sort_keys=True)}"
            ),
        },
    ]


def create_langchain_plan_provider(model: Any | None = None) -> PlanProvider:
    """Create a lazy structured-output planner provider."""

    configured_model = model or DEFAULT_MODEL
    structured_planner: Any | None = None

    def provider(
        payload: PlannerProviderInput,
    ) -> AgentExecutionPlan | Mapping[str, Any]:
        nonlocal structured_planner
        if structured_planner is None:
            llm = (
                init_chat_model(configured_model, configurable_fields=["model"])
                if isinstance(configured_model, str)
                else configured_model
            )
            structured_planner = llm.with_structured_output(AgentExecutionPlan)
        output = structured_planner.invoke(_build_langchain_planner_messages(payload))
        return _coerce_plan_provider_output(output)

    return provider


class AgentPlanner(Protocol):
    """Planner boundary consumed by the Supervisor graph node."""

    def build_plan(
        self,
        routes: Sequence[str],
        *,
        message: str,
        routing_reasons: Mapping[str, str] | None = None,
        run_id: str | None = None,
        parallel_enabled: bool = False,
        max_parallelism: int = 1,
        retry_policy: AgentTaskRetryPolicy | None = None,
    ) -> AgentExecutionPlan:
        """Return one policy-compliant execution plan."""


def build_deterministic_agent_plan(
    routes: Sequence[str],
    *,
    routing_reasons: Mapping[str, str] | None = None,
    run_id: str | None = None,
    parallel_enabled: bool = False,
    max_parallelism: int = 1,
    retry_policy: AgentTaskRetryPolicy | None = None,
) -> AgentExecutionPlan:
    """Describe independent reads and apply the server-owned execution mode."""

    route_order = list(routes)
    unknown_routes = set(route_order).difference(ROUTE_INTENTS)
    if unknown_routes:
        raise ValueError("Agent plans may contain only registered read routes.")
    if len(route_order) != len(set(route_order)):
        raise ValueError("Agent plans may contain each read route at most once.")

    reasons = dict(routing_reasons or {})
    plan_identity = run_id or "|".join(route_order) or "empty-read-plan"
    use_parallel = parallel_enabled and len(route_order) > 1
    execution_mode = (
        AgentPlanExecutionMode.BOUNDED_PARALLEL
        if use_parallel
        else AgentPlanExecutionMode.SEQUENTIAL
    )
    resolved_parallelism = (
        min(max(1, max_parallelism), len(route_order)) if use_parallel else 1
    )
    resolved_retry_policy = retry_policy or AgentTaskRetryPolicy()
    return AgentExecutionPlan(
        plan_id=(
            f"{run_id}:read-plan"
            if run_id
            else str(uuid5(NAMESPACE_URL, plan_identity))
        ),
        run_id=run_id,
        planner_type="deterministic_route_plan",
        execution_mode=execution_mode,
        max_parallelism=resolved_parallelism,
        steps=[
            AgentPlanStep(
                step_id=f"read-{index}-{route}",
                recipient=route,
                intent=ROUTE_INTENTS[route],
                depends_on=[],
                parallel_eligible=True,
                retry_policy=resolved_retry_policy,
                metadata={"routing_reason": reasons.get(route)},
            )
            for index, route in enumerate(route_order, start=1)
        ],
        metadata={
            "route_order": route_order,
            "parallel_execution_enabled": use_parallel,
        },
    )


class DeterministicAgentPlanner:
    """Compile the canonical route plan without calling a provider."""

    def build_plan(
        self,
        routes: Sequence[str],
        *,
        message: str,
        routing_reasons: Mapping[str, str] | None = None,
        run_id: str | None = None,
        parallel_enabled: bool = False,
        max_parallelism: int = 1,
        retry_policy: AgentTaskRetryPolicy | None = None,
    ) -> AgentExecutionPlan:
        del message
        return build_deterministic_agent_plan(
            routes,
            routing_reasons=routing_reasons,
            run_id=run_id,
            parallel_enabled=parallel_enabled,
            max_parallelism=max_parallelism,
            retry_policy=retry_policy,
        )


class ValidatedProviderPlanner:
    """Validate an untrusted plan proposal, then compile a canonical plan."""

    def __init__(
        self,
        plan_provider: PlanProvider | None = None,
        *,
        provider_type: str | None = None,
        model_name: str | None = None,
        fallback_planner: AgentPlanner | None = None,
    ) -> None:
        self.plan_provider = plan_provider
        self.provider_type = provider_type or (
            "custom_callable" if plan_provider is not None else None
        )
        self.model_name = model_name
        self.fallback_planner = fallback_planner or DeterministicAgentPlanner()

    def build_plan(
        self,
        routes: Sequence[str],
        *,
        message: str,
        routing_reasons: Mapping[str, str] | None = None,
        run_id: str | None = None,
        parallel_enabled: bool = False,
        max_parallelism: int = 1,
        retry_policy: AgentTaskRetryPolicy | None = None,
    ) -> AgentExecutionPlan:
        baseline = self.fallback_planner.build_plan(
            routes,
            message=message,
            routing_reasons=routing_reasons,
            run_id=run_id,
            parallel_enabled=parallel_enabled,
            max_parallelism=max_parallelism,
            retry_policy=retry_policy,
        )
        if not baseline.steps:
            return baseline.model_copy(
                update={
                    "metadata": {
                        **baseline.metadata,
                        "planner_provider_skipped": "no_read_routes",
                    }
                }
            )
        if self.plan_provider is None:
            return self._fallback(baseline, "provider_not_configured")

        payload: PlannerProviderInput = {
            "message": message,
            "routes": list(routes),
            "routing_reasons": dict(routing_reasons or {}),
            "baseline_plan": baseline.model_dump(mode="json"),
        }
        try:
            proposal = AgentExecutionPlan.model_validate(self.plan_provider(payload))
        except Exception:
            return self._fallback(baseline, "provider_error_or_invalid_contract")

        invalid_reason = self._invalid_reason(proposal, baseline)
        if invalid_reason is not None:
            return self._fallback(baseline, invalid_reason)

        return baseline.model_copy(
            update={
                "planner_type": "validated_provider_plan",
                "metadata": {
                    **baseline.metadata,
                    "planner_provider": self.provider_type,
                    "planner_model": self.model_name,
                    "provider_validated": True,
                },
            }
        )

    def _fallback(
        self,
        baseline: AgentExecutionPlan,
        reason: str,
    ) -> AgentExecutionPlan:
        return baseline.model_copy(
            update={
                "planner_type": "provider_fallback",
                "metadata": {
                    **baseline.metadata,
                    "planner_provider": self.provider_type,
                    "planner_model": self.model_name,
                    "planner_fallback_reason": reason,
                    "fallback_planner_type": baseline.planner_type,
                },
            }
        )

    @staticmethod
    def _invalid_reason(
        proposal: AgentExecutionPlan,
        baseline: AgentExecutionPlan,
    ) -> str | None:
        if proposal.run_id != baseline.run_id:
            return "run_identity_mismatch"
        if proposal.execution_mode != baseline.execution_mode:
            return "execution_mode_outside_policy"
        if proposal.max_parallelism != baseline.max_parallelism:
            return "parallelism_outside_policy"

        proposed_steps = [
            (
                step.step_id,
                step.recipient,
                step.intent,
                step.depends_on,
                step.parallel_eligible,
                step.retry_policy,
            )
            for step in proposal.steps
        ]
        baseline_steps = [
            (
                step.step_id,
                step.recipient,
                step.intent,
                step.depends_on,
                step.parallel_eligible,
                step.retry_policy,
            )
            for step in baseline.steps
        ]
        if [step[1] for step in proposed_steps] != [step[1] for step in baseline_steps]:
            return "routes_outside_supervisor_decision"
        if proposed_steps != baseline_steps:
            return "step_contract_outside_policy"
        return None


def create_agent_planner(
    planner_mode: str | None = None,
    *,
    model: Any | None = None,
    plan_provider: PlanProvider | None = None,
) -> AgentPlanner:
    """Create a deterministic or explicitly enabled structured planner."""

    normalized = (planner_mode or "deterministic").strip().lower()
    if normalized != "llm":
        return DeterministicAgentPlanner()
    return ValidatedProviderPlanner(
        plan_provider or create_langchain_plan_provider(model=model),
        provider_type=(
            "custom_callable"
            if plan_provider is not None
            else "langchain_structured_output"
        ),
        model_name=(
            None if plan_provider is not None else _describe_planner_model(model)
        ),
    )


__all__ = [
    "AgentPlanner",
    "DeterministicAgentPlanner",
    "PlanProvider",
    "PlannerProviderInput",
    "ROUTE_INTENTS",
    "ValidatedProviderPlanner",
    "build_deterministic_agent_plan",
    "create_agent_planner",
    "create_langchain_plan_provider",
]
