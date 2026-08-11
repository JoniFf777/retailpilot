"""State schema for the ShopMind V3 read-only multi-agent path."""

from typing import Any, Optional, TypedDict


class ShopMindMultiAgentState(TypedDict, total=False):
    messages: list[Any]
    user_id: str
    thread_id: Optional[str]

    intent: Optional[str]
    supervisor_decision: Optional[dict[str, Any]]
    execution_plan: Optional[dict[str, Any]]
    parallel_execution: Optional[dict[str, Any]]
    routes: list[str]
    executed_routes: list[str]
    current_route: Optional[str]
    plan_step_id: Optional[str]
    plan_step_retry_policy: Optional[dict[str, Any]]

    product_summary: Optional[dict[str, Any]]
    rag_summary: Optional[dict[str, Any]]
    preference_summary: Optional[dict[str, Any]]
    evidence_references: list[dict[str, Any]]
    delegated_usage: list[dict[str, Any]]

    # Phase 1B structured recommendation state.  Every value is JSON-compatible
    # so graph snapshots can be inspected without ORM/session objects.
    recommendation_gate: Optional[dict[str, Any]]
    structured_constraints: Optional[dict[str, Any]]
    catalog_candidates: list[dict[str, Any]]
    recommendation_result: Optional[dict[str, Any]]
    recommendation_diagnostics: Optional[dict[str, Any]]
    top_k_product_evidence: dict[str, list[dict[str, Any]]]
    policy_evidence: list[dict[str, Any]]
    recommendation: Optional[dict[str, Any]]

    decision: Optional[dict[str, Any]]
    final_response: Optional[str]
    handoff_reason: Optional[str]
    safety_flags: list[str]
    tool_calls: list[str]
    agent_steps: list[dict[str, Any]]
