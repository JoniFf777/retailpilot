import pytest

from agents.shopmind_multi_agent.planning import (
    DeterministicAgentPlanner,
    ValidatedProviderPlanner,
    build_deterministic_agent_plan,
    create_agent_planner,
    create_langchain_plan_provider,
)
from agents.shopmind_multi_agent.supervisor import supervisor_node
from app.runtime import (
    AgentExecutionPlan,
    AgentTaskRetryOwner,
    AgentTaskRetryPolicy,
    AgentTransportFailureCode,
)


class FakeStructuredPlannerModel:
    def __init__(self, output: dict) -> None:
        self.output = output
        self.messages = None

    def invoke(self, messages: list[dict[str, str]]) -> dict:
        self.messages = messages
        return self.output


class FakePlannerModel:
    def __init__(self, output: dict) -> None:
        self.output = output
        self.schema = None
        self.structured_model: FakeStructuredPlannerModel | None = None

    def with_structured_output(self, schema):
        self.schema = schema
        self.structured_model = FakeStructuredPlannerModel(self.output)
        return self.structured_model


def test_deterministic_plan_describes_independent_reads_but_stays_sequential() -> None:
    plan = build_deterministic_agent_plan(
        ["product_agent", "rag_agent", "preference_agent"],
        routing_reasons={"rag_agent": "matched_policy"},
        run_id="run-1",
    )

    assert plan.plan_id == "run-1:read-plan"
    assert plan.execution_mode == "sequential"
    assert plan.max_parallelism == 1
    assert [step.recipient for step in plan.steps] == [
        "product_agent",
        "rag_agent",
        "preference_agent",
    ]
    assert all(step.depends_on == [] for step in plan.steps)
    assert all(step.parallel_eligible for step in plan.steps)
    assert plan.steps[1].metadata["routing_reason"] == "matched_policy"
    assert plan.metadata["parallel_execution_enabled"] is False


def test_deterministic_plan_rejects_unknown_or_duplicate_routes() -> None:
    with pytest.raises(ValueError, match="registered read routes"):
        build_deterministic_agent_plan(["decision_agent"])
    with pytest.raises(ValueError, match="at most once"):
        build_deterministic_agent_plan(["rag_agent", "rag_agent"])


def test_deterministic_plan_requires_opt_in_and_multiple_routes_for_parallelism() -> None:
    parallel = build_deterministic_agent_plan(
        ["product_agent", "rag_agent", "preference_agent"],
        parallel_enabled=True,
        max_parallelism=2,
    )
    single_route = build_deterministic_agent_plan(
        ["rag_agent"],
        parallel_enabled=True,
        max_parallelism=3,
    )

    assert parallel.execution_mode == "bounded_parallel"
    assert parallel.max_parallelism == 2
    assert parallel.metadata["parallel_execution_enabled"] is True
    assert single_route.execution_mode == "sequential"
    assert single_route.max_parallelism == 1


def test_deterministic_plan_applies_server_owned_retry_policy_to_every_step() -> None:
    retry_policy = AgentTaskRetryPolicy(
        owner=AgentTaskRetryOwner.PLAN_EXECUTOR,
        max_attempts=2,
        retryable_failure_codes={AgentTransportFailureCode.UNAVAILABLE},
    )

    plan = build_deterministic_agent_plan(
        ["product_agent", "rag_agent"],
        retry_policy=retry_policy,
    )

    assert all(step.retry_policy == retry_policy for step in plan.steps)


def test_validated_provider_planner_recompiles_accepted_proposal() -> None:
    received: list[dict] = []

    def provider(payload):
        received.append(payload)
        proposal = dict(payload["baseline_plan"])
        proposal["plan_id"] = "provider-controlled-id"
        proposal["planner_type"] = "provider-controlled-type"
        proposal["metadata"] = {"untrusted": True}
        return proposal

    planner = ValidatedProviderPlanner(
        provider,
        provider_type="test_structured_provider",
    )
    plan = planner.build_plan(
        ["product_agent", "rag_agent"],
        message="recommend a keyboard and check return policy",
        routing_reasons={"rag_agent": "matched_policy"},
        run_id="run-1",
        parallel_enabled=True,
        max_parallelism=2,
    )

    assert received[0]["routes"] == ["product_agent", "rag_agent"]
    assert plan.plan_id == "run-1:read-plan"
    assert plan.planner_type == "validated_provider_plan"
    assert plan.metadata["planner_provider"] == "test_structured_provider"
    assert plan.metadata["provider_validated"] is True
    assert "untrusted" not in plan.metadata


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (
            lambda plan: plan["steps"][0].update(
                {"recipient": "decision_agent"}
            ),
            "routes_outside_supervisor_decision",
        ),
        (
            lambda plan: plan["steps"][1].update(
                {"depends_on": ["read-1-product_agent"]}
            ),
            "step_contract_outside_policy",
        ),
        (
            lambda plan: plan.update({"max_parallelism": 3}),
            "parallelism_outside_policy",
        ),
        (
            lambda plan: plan.update({"run_id": "other-run"}),
            "run_identity_mismatch",
        ),
        (
            lambda plan: plan["steps"][0].update(
                {
                    "retry_policy": {
                        "owner": "plan_executor",
                        "max_attempts": 3,
                        "retryable_failure_codes": ["agent.transport_timeout"],
                    }
                }
            ),
            "step_contract_outside_policy",
        ),
    ],
)
def test_provider_planner_falls_back_when_proposal_exceeds_policy(
    mutate,
    reason: str,
) -> None:
    def provider(payload):
        proposal = payload["baseline_plan"]
        mutate(proposal)
        return proposal

    plan = ValidatedProviderPlanner(provider).build_plan(
        ["product_agent", "rag_agent"],
        message="recommend a keyboard and check return policy",
        run_id="run-1",
        parallel_enabled=True,
        max_parallelism=2,
    )

    assert plan.planner_type == "provider_fallback"
    assert plan.metadata["planner_fallback_reason"] == reason
    assert plan.metadata["fallback_planner_type"] == "deterministic_route_plan"
    assert [step.recipient for step in plan.steps] == [
        "product_agent",
        "rag_agent",
    ]
    assert all(step.depends_on == [] for step in plan.steps)
    assert plan.max_parallelism == 2


def test_provider_planner_falls_back_without_leaking_provider_error() -> None:
    def failing_provider(payload):
        raise RuntimeError("private provider detail")

    plan = ValidatedProviderPlanner(failing_provider).build_plan(
        ["product_agent"],
        message="recommend a keyboard",
    )

    assert plan.planner_type == "provider_fallback"
    assert (
        plan.metadata["planner_fallback_reason"]
        == "provider_error_or_invalid_contract"
    )
    assert "private provider detail" not in str(plan.model_dump(mode="json"))


def test_supervisor_records_validated_planner_fallback_metadata() -> None:
    planner = ValidatedProviderPlanner(
        lambda payload: {
            **payload["baseline_plan"],
            "execution_mode": "bounded_parallel",
            "max_parallelism": 3,
        },
        provider_type="test_provider",
    )

    result = supervisor_node(
        {
            "messages": [{"role": "user", "content": "recommend a keyboard"}],
            "user_id": "USER-001",
            "agent_steps": [],
            "safety_flags": [],
            "tool_calls": [],
        },
        planner=planner,
    )

    assert result["routes"] == ["product_agent"]
    assert result["execution_plan"]["planner_type"] == "provider_fallback"
    assert result["execution_plan"]["execution_mode"] == "sequential"
    supervisor_step = result["agent_steps"][0]
    assert supervisor_step["planner_provider"] == "test_provider"
    assert (
        supervisor_step["planner_fallback_reason"]
        == "execution_mode_outside_policy"
    )
    assert supervisor_step["fallback_planner_type"] == "deterministic_route_plan"


def test_agent_planner_factory_defaults_to_deterministic() -> None:
    assert isinstance(create_agent_planner(), DeterministicAgentPlanner)
    assert isinstance(
        create_agent_planner(
            "llm",
            plan_provider=lambda payload: payload["baseline_plan"],
        ),
        ValidatedProviderPlanner,
    )
    assert isinstance(create_agent_planner("unknown"), DeterministicAgentPlanner)


def test_langchain_planner_provider_uses_structured_plan_contract() -> None:
    baseline = build_deterministic_agent_plan(
        ["product_agent", "rag_agent"],
        run_id="run-1",
        parallel_enabled=True,
        max_parallelism=2,
    )
    fake_model = FakePlannerModel(baseline.model_dump(mode="json"))
    provider = create_langchain_plan_provider(fake_model)

    proposal = provider(
        {
            "message": "recommend a keyboard and check return policy",
            "routes": ["product_agent", "rag_agent"],
            "routing_reasons": {},
            "baseline_plan": baseline.model_dump(mode="json"),
        }
    )

    assert fake_model.schema is AgentExecutionPlan
    assert fake_model.structured_model is not None
    messages = fake_model.structured_model.messages
    assert messages is not None
    assert "Do not add" in messages[0]["content"]
    assert "Supervisor routes: product_agent, rag_agent" in messages[1]["content"]
    assert proposal["run_id"] == "run-1"


def test_llm_planner_factory_is_lazy_and_records_model_metadata() -> None:
    baseline = build_deterministic_agent_plan(["product_agent"], run_id="run-1")
    fake_model = FakePlannerModel(baseline.model_dump(mode="json"))
    planner = create_agent_planner("llm", model=fake_model)

    assert fake_model.structured_model is None
    plan = planner.build_plan(
        ["product_agent"],
        message="recommend a keyboard",
        run_id="run-1",
    )

    assert plan.planner_type == "validated_provider_plan"
    assert plan.metadata["planner_provider"] == "langchain_structured_output"
    assert plan.metadata["planner_model"] == "FakePlannerModel"
    assert fake_model.structured_model is not None


def test_provider_planner_skips_model_for_write_path_without_read_routes() -> None:
    calls = 0

    def provider(payload):
        nonlocal calls
        calls += 1
        raise AssertionError("provider must not run for write handoff")

    plan = ValidatedProviderPlanner(provider).build_plan(
        [],
        message="add this keyboard to cart",
        run_id="run-1",
    )

    assert calls == 0
    assert plan.steps == []
    assert plan.planner_type == "deterministic_route_plan"
    assert plan.metadata["planner_provider_skipped"] == "no_read_routes"
