import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier, Lock

import pytest
from pydantic import BaseModel, Field, ValidationError

from agents.shopmind_multi_agent.permissions import AGENT_TOOL_ALLOWLIST
from app.runtime.contracts import (
    DatabaseAccess,
    RunBudget,
    RunContext,
    RunRequest,
    RuntimePolicy,
    ToolCallStatus,
    ToolSideEffectClass,
    ToolResourcePolicy,
    utc_now,
)
from app.runtime.tool_gateway import (
    ToolCapability,
    ToolGateway,
    ToolGatewayError,
    ToolGatewayExecutionError,
    V3_TOOL_CAPABILITY_POLICIES,
)


class ProfileArguments(BaseModel):
    user_id: str
    thread_id: str
    query: str = Field(min_length=1)


class FakeTool:
    name = "get_user_profile"
    args_schema = ProfileArguments

    def __init__(self, result: str = "profile") -> None:
        self.result = result
        self.calls = 0

    def invoke(self, arguments: dict[str, str]) -> str:
        self.calls += 1
        return self.result


class SensitiveArguments(BaseModel):
    user_id: str
    thread_id: str


class SensitiveTool(FakeTool):
    name = "confirm_add_to_cart"
    args_schema = SensitiveArguments


class FailingTool(FakeTool):
    def invoke(self, arguments: dict[str, str]) -> str:
        self.calls += 1
        raise RuntimeError("provider detail must not reach the runtime result")


class SlowTool(FakeTool):
    def invoke(self, arguments: dict[str, str]) -> str:
        self.calls += 1
        time.sleep(0.01)
        return self.result


class ConcurrentTool(FakeTool):
    def __init__(self) -> None:
        super().__init__()
        self._lock = Lock()

    def invoke(self, arguments: dict[str, str]) -> str:
        with self._lock:
            self.calls += 1
        time.sleep(0.005)
        return self.result


def make_context(
    *,
    allow_sensitive_tools: bool = False,
    max_tool_calls: int | None = None,
    deadline_expired: bool = False,
    cancellation_requested: bool = False,
) -> RunContext:
    request = RunRequest(
        operation="chat",
        user_id="user-1",
        thread_id="thread-1",
        policy=RuntimePolicy(allow_sensitive_tools=allow_sensitive_tools),
        budget=RunBudget(max_tool_calls=max_tool_calls),
        deadline_at=utc_now() - timedelta(seconds=1) if deadline_expired else None,
    )
    return RunContext(
        request=request,
        policy=request.policy,
        budget=request.budget,
        cancellation_requested=cancellation_requested,
    )


def register_read_gateway(tool: FakeTool) -> ToolGateway:
    return ToolGateway(
        [
            ToolCapability(
                name=tool.name,
                allowed_agents=frozenset({"preference_agent"}),
                side_effect_class=ToolSideEffectClass.READ,
            )
        ]
    )


def test_gateway_rejects_duplicate_or_blank_capability_during_initialization() -> None:
    capability = ToolCapability(
        name="get_user_profile",
        allowed_agents=frozenset({"preference_agent"}),
        side_effect_class=ToolSideEffectClass.READ,
    )

    with pytest.raises(ToolGatewayError, match="already registered"):
        ToolGateway((capability, capability))
    with pytest.raises(ToolGatewayError, match="name is required"):
        ToolGateway((
            ToolCapability(
                name=" ",
                allowed_agents=frozenset({"preference_agent"}),
            ),
        ))


def test_gateway_assigns_database_resource_policy_to_registered_v3_tools() -> None:
    gateway = ToolGateway.from_allowlist(
        {
            "product_agent": {
                "search_products",
                "get_product_detail",
                "compare_products",
            },
            "write_handoff": {"prepare_add_to_cart"},
            "confirmation_boundary": {"confirm_add_to_cart"},
        }
    )

    assert gateway.capability_for("search_products").resource_policy.database_access == (
        DatabaseAccess.READ
    )
    assert gateway.capability_for("compare_products").resource_policy.database_access == (
        DatabaseAccess.READ
    )
    assert gateway.capability_for("prepare_add_to_cart").resource_policy.database_access == (
        DatabaseAccess.WRITE
    )
    assert gateway.capability_for("confirm_add_to_cart").resource_policy.database_access == (
        DatabaseAccess.WRITE
    )


def test_strict_gateway_requires_explicit_policy_for_every_registered_tool() -> None:
    registered_tools = {
        tool_name
        for tool_names in AGENT_TOOL_ALLOWLIST.values()
        for tool_name in tool_names
    }

    gateway = ToolGateway.from_allowlist(
        AGENT_TOOL_ALLOWLIST,
        require_explicit_capabilities=True,
    )

    assert set(V3_TOOL_CAPABILITY_POLICIES) == registered_tools
    assert {gateway.capability_for(tool_name).name for tool_name in registered_tools} == (
        registered_tools
    )
    for tool_name, policy in V3_TOOL_CAPABILITY_POLICIES.items():
        expected_agents = frozenset(
            agent_name
            for agent_name, tool_names in AGENT_TOOL_ALLOWLIST.items()
            if tool_name in tool_names
        )
        assert policy.allowed_agents == expected_agents
    with pytest.raises(TypeError):
        V3_TOOL_CAPABILITY_POLICIES["unclassified_tool"] = (  # type: ignore[index]
            V3_TOOL_CAPABILITY_POLICIES["search_products"]
        )
    with pytest.raises(ValidationError, match="frozen"):
        V3_TOOL_CAPABILITY_POLICIES[
            "search_products"
        ].resource_policy.database_access = DatabaseAccess.WRITE
    with pytest.raises(ToolGatewayError, match="requires an explicit"):
        ToolGateway.from_allowlist(
            {"product_agent": {"unclassified_tool"}},
            require_explicit_capabilities=True,
        )
    with pytest.raises(ToolGatewayError, match="agent assignment"):
        ToolGateway.from_allowlist(
            {"rag_agent": {"search_products"}},
            require_explicit_capabilities=True,
        )


def test_gateway_rejects_resource_policy_that_conflicts_with_side_effect_class() -> None:
    with pytest.raises(ToolGatewayError, match="Database write capabilities"):
        ToolGateway(
            (
                ToolCapability(
                    name="unsafe_write",
                    allowed_agents=frozenset({"write_agent"}),
                    side_effect_class=ToolSideEffectClass.READ,
                    resource_policy=ToolResourcePolicy(
                        database_access=DatabaseAccess.WRITE
                    ),
                ),
            )
        )


@pytest.mark.parametrize(
    ("side_effect_class", "requires_confirmation", "message"),
    [
        (
            ToolSideEffectClass.SENSITIVE_WRITE,
            False,
            "Sensitive write capabilities",
        ),
        (
            ToolSideEffectClass.READ,
            True,
            "Confirmation requirements",
        ),
    ],
)
def test_gateway_rejects_confirmation_policy_that_conflicts_with_side_effect_class(
    side_effect_class: ToolSideEffectClass,
    requires_confirmation: bool,
    message: str,
) -> None:
    with pytest.raises(ToolGatewayError, match=message):
        ToolGateway(
            (
                ToolCapability(
                    name="invalid_confirmation_policy",
                    allowed_agents=frozenset({"write_agent"}),
                    side_effect_class=side_effect_class,
                    requires_confirmation=requires_confirmation,
                ),
            )
        )


def test_network_resource_policy_requires_bare_https_host_allowlist() -> None:
    with pytest.raises(ValueError, match="require an HTTPS host allowlist"):
        ToolResourcePolicy(network_access=True)
    with pytest.raises(ValueError, match="bare lowercase hosts"):
        ToolResourcePolicy(network_access=True, allowed_https_hosts={"https://api.example.com"})

    policy = ToolResourcePolicy(
        network_access=True,
        allowed_https_hosts={"api.example.com"},
    )

    assert policy.allowed_https_hosts == frozenset({"api.example.com"})


def test_gateway_validates_arguments_before_invocation_and_records_call() -> None:
    tool = FakeTool()
    gateway = register_read_gateway(tool)
    context = make_context()

    result, record = gateway.invoke(
        agent_name="preference_agent",
        tool=tool,
        arguments={
            "user_id": "user-1",
            "thread_id": "thread-1",
            "query": "keyboard",
        },
        context=context,
    )

    assert result == "profile"
    assert tool.calls == 1
    assert record.tool_name == tool.name
    assert record.argument_hash
    assert record.completed_at is not None
    assert record.duration_ms is not None
    assert record.requires_confirmation is False
    assert context.metadata["tool_gateway_call_count"] == 1


def test_gateway_rejects_invalid_arguments_before_side_effect() -> None:
    tool = FakeTool()
    gateway = register_read_gateway(tool)

    with pytest.raises(ToolGatewayError, match="Invalid arguments"):
        gateway.invoke(
            agent_name="preference_agent",
            tool=tool,
            arguments={"user_id": "user-1", "thread_id": "thread-1", "query": ""},
            context=make_context(),
        )

    assert tool.calls == 0


@pytest.mark.parametrize(
    "arguments, message",
    [
        (
            {"user_id": "other-user", "thread_id": "thread-1", "query": "x"},
            "user_id",
        ),
        (
            {"user_id": "user-1", "thread_id": "other-thread", "query": "x"},
            "thread_id",
        ),
    ],
)
def test_gateway_enforces_user_and_thread_ownership(
    arguments: dict[str, str], message: str
) -> None:
    tool = FakeTool()
    gateway = register_read_gateway(tool)

    with pytest.raises(ToolGatewayError, match=message):
        gateway.invoke(
            agent_name="preference_agent",
            tool=tool,
            arguments=arguments,
            context=make_context(),
        )

    assert tool.calls == 0


def test_gateway_enforces_per_run_tool_budget() -> None:
    tool = FakeTool()
    gateway = register_read_gateway(tool)
    context = make_context(max_tool_calls=1)
    arguments = {"user_id": "user-1", "thread_id": "thread-1", "query": "x"}

    gateway.invoke(
        agent_name="preference_agent",
        tool=tool,
        arguments=arguments,
        context=context,
    )

    with pytest.raises(ToolGatewayError, match="budget"):
        gateway.invoke(
            agent_name="preference_agent",
            tool=tool,
            arguments=arguments,
            context=context,
        )

    assert tool.calls == 1


def test_gateway_reserves_concurrent_budget_and_orders_audit_records() -> None:
    tool = ConcurrentTool()
    gateway = register_read_gateway(tool)
    context = make_context(max_tool_calls=3)
    start = Barrier(8)

    def invoke(index: int) -> bool:
        start.wait(timeout=2)
        try:
            gateway.invoke(
                agent_name="preference_agent",
                tool=tool,
                arguments={
                    "user_id": "user-1",
                    "thread_id": "thread-1",
                    "query": f"query-{index}",
                },
                context=context,
            )
            return True
        except ToolGatewayError:
            return False

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(invoke, range(8)))

    snapshot = context.metadata_snapshot()
    records = snapshot["tool_call_records"]
    assert sum(results) == 3
    assert tool.calls == 3
    assert snapshot["tool_gateway_call_count"] == 3
    assert len(records) == 3
    assert [record["audit_sequence"] for record in records] == [1, 2, 3]
    assert len({record["tool_call_id"] for record in records}) == 3

    records.append({"tool_call_id": "snapshot-only"})
    assert len(context.metadata_snapshot()["tool_call_records"]) == 3


def test_gateway_skips_tool_when_deadline_has_elapsed_before_invocation() -> None:
    tool = FakeTool()
    gateway = register_read_gateway(tool)
    context = make_context(deadline_expired=True)

    with pytest.raises(ToolGatewayExecutionError) as exc_info:
        gateway.invoke(
            agent_name="preference_agent",
            tool=tool,
            arguments={"user_id": "user-1", "thread_id": "thread-1", "query": "x"},
            context=context,
        )

    record = exc_info.value.tool_call_record
    assert tool.calls == 0
    assert record.status == ToolCallStatus.SKIPPED
    assert record.result_metadata["error_code"] == "tool.deadline_exceeded"
    assert context.metadata["tool_gateway_call_count"] == 1


def test_gateway_skips_tool_when_cancellation_was_requested() -> None:
    tool = FakeTool()
    gateway = register_read_gateway(tool)
    context = make_context(cancellation_requested=True)

    with pytest.raises(ToolGatewayExecutionError) as exc_info:
        gateway.invoke(
            agent_name="preference_agent",
            tool=tool,
            arguments={"user_id": "user-1", "thread_id": "thread-1", "query": "x"},
            context=context,
        )

    record = exc_info.value.tool_call_record
    assert tool.calls == 0
    assert record.status == ToolCallStatus.SKIPPED
    assert record.result_metadata["error_code"] == "tool.cancelled"
    assert context.metadata["tool_call_records"][0]["tool_call_id"] == record.tool_call_id


def test_gateway_audits_capability_duration_without_rewriting_success() -> None:
    tool = SlowTool()
    gateway = ToolGateway(
        [
            ToolCapability(
                name=tool.name,
                allowed_agents=frozenset({"preference_agent"}),
                side_effect_class=ToolSideEffectClass.READ,
                max_duration_ms=1,
            )
        ]
    )
    context = make_context()

    result, record = gateway.invoke(
        agent_name="preference_agent",
        tool=tool,
        arguments={"user_id": "user-1", "thread_id": "thread-1", "query": "x"},
        context=context,
    )

    assert result == "profile"
    assert tool.calls == 1
    assert record.status == ToolCallStatus.COMPLETED
    assert record.result_metadata == {
        "duration_limit_ms": 1,
        "duration_limit_exceeded": True,
    }


def test_gateway_requires_policy_for_sensitive_tools() -> None:
    tool = SensitiveTool()
    gateway = ToolGateway.from_allowlist(
        {"write_agent": {"confirm_add_to_cart"}}
    )
    arguments = {"user_id": "user-1", "thread_id": "thread-1"}

    with pytest.raises(ToolGatewayError, match="approved runtime policy"):
        gateway.invoke(
            agent_name="write_agent",
            tool=tool,
            arguments=arguments,
            context=make_context(),
        )

    result, record = gateway.invoke(
        agent_name="write_agent",
        tool=tool,
        arguments=arguments,
        context=make_context(allow_sensitive_tools=True),
    )
    assert result == "profile"
    assert record.side_effect_class == ToolSideEffectClass.SENSITIVE_WRITE
    assert record.requires_confirmation is True
    assert record.resource_policy.database_access == DatabaseAccess.WRITE


def test_gateway_allows_pending_action_preparation_without_sensitive_policy() -> None:
    tool = FakeTool()
    tool.name = "prepare_add_to_cart"
    gateway = ToolGateway.from_allowlist({"write_handoff": {tool.name}})

    result, record = gateway.invoke(
        agent_name="write_handoff",
        tool=tool,
        arguments={
            "user_id": "user-1",
            "thread_id": "thread-1",
            "query": "keyboard",
        },
        context=make_context(),
    )

    assert result == "profile"
    assert record.side_effect_class == ToolSideEffectClass.WRITE
    assert record.requires_confirmation is True
    assert record.resource_policy.database_access == DatabaseAccess.WRITE


def test_gateway_rejects_oversized_output() -> None:
    tool = FakeTool(result="too long")
    gateway = ToolGateway(
        [
            ToolCapability(
                name=tool.name,
                allowed_agents=frozenset({"preference_agent"}),
                side_effect_class=ToolSideEffectClass.READ,
                max_output_chars=3,
            )
        ]
    )

    with pytest.raises(ToolGatewayError, match="output limit"):
        gateway.invoke(
            agent_name="preference_agent",
            tool=tool,
            arguments={"user_id": "user-1", "thread_id": "thread-1", "query": "x"},
            context=make_context(),
        )

    assert tool.calls == 1


def test_gateway_records_failed_tool_attempt_without_leaking_exception_detail() -> None:
    tool = FailingTool()
    gateway = register_read_gateway(tool)
    context = make_context()

    with pytest.raises(ToolGatewayExecutionError) as exc_info:
        gateway.invoke(
            agent_name="preference_agent",
            tool=tool,
            arguments={"user_id": "user-1", "thread_id": "thread-1", "query": "x"},
            context=context,
        )

    record = exc_info.value.tool_call_record
    assert tool.calls == 1
    assert record.status == ToolCallStatus.FAILED
    assert record.completed_at is not None
    assert record.result_metadata == {
        "error_code": "tool.execution_failed",
        "exception_type": "RuntimeError",
    }
    assert context.metadata["tool_gateway_call_count"] == 1
    assert context.metadata["tool_call_records"][0]["tool_call_id"] == record.tool_call_id


def test_gateway_rejects_unregistered_capability() -> None:
    tool = FakeTool()

    with pytest.raises(ToolGatewayError, match="not registered"):
        ToolGateway().validate_invocation(
            agent_name="preference_agent",
            tool=tool,
            arguments={"user_id": "user-1", "thread_id": "thread-1", "query": "x"},
        )
