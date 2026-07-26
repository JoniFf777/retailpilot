from agents.shopmind_multi_agent import create_shopmind_agent_adapter_registry
from app.runtime import (
    DelegationBudgetGuard,
    InProcessAgentAdapter,
    PolicyEnforcedAgentAdapter,
    RunBudget,
)


def test_default_registry_owns_all_specialists_and_shares_trusted_guard() -> None:
    guard = DelegationBudgetGuard(trusted_budget=RunBudget(max_steps=3))

    registry = create_shopmind_agent_adapter_registry(
        product_tools=None,
        rag_tools=None,
        preference_tools=None,
        delegation_guard=guard,
    )

    assert registry.registered_agents == (
        "product_agent",
        "rag_agent",
        "preference_agent",
    )
    assert registry.policy_required is True
    for recipient in registry.registered_agents:
        adapter = registry.resolve(recipient)
        assert isinstance(adapter, PolicyEnforcedAgentAdapter)
        assert adapter.delegation_guard is guard
        assert isinstance(adapter.adapter, InProcessAgentAdapter)
