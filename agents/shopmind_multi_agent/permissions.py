"""Runtime tool permission guard for ShopMind V3 agents."""

from dataclasses import dataclass
from typing import Any, Iterable, Mapping


class ToolPermissionError(PermissionError):
    """Raised when an agent attempts to call a tool outside its allowlist."""


AGENT_TOOL_ALLOWLIST: dict[str, set[str]] = {
    "supervisor": set(),
    "decision_agent": set(),
    "product_agent": {
        "search_products",
        "get_product_detail",
        "compare_products",
    },
    "rag_agent": {
        "search_product_docs",
        "search_policy_docs",
    },
    "preference_agent": {
        "get_user_preferences",
    },
    "confirmation_boundary": {
        "confirm_add_to_cart",
        "confirm_save_preference",
        "cancel_pending_action",
    },
    "write_handoff": {
        "prepare_add_to_cart",
        "prepare_save_preference",
    },
}


@dataclass(frozen=True)
class PermissionedTool:
    """Small wrapper that enforces allowlists before delegating to a real tool."""

    agent_name: str
    wrapped_tool: Any
    runtime_context: Any | None = None

    @property
    def name(self) -> str:
        return self.wrapped_tool.name

    @property
    def description(self) -> str:
        return getattr(self.wrapped_tool, "description", "")

    @property
    def args_schema(self) -> Any:
        return getattr(self.wrapped_tool, "args_schema", None)

    def invoke(self, tool_input: Any, *args: Any, **kwargs: Any) -> Any:
        assert_tool_allowed(self.agent_name, self.name)
        from app.runtime.tool_gateway import ToolGateway

        gateway = ToolGateway.from_allowlist(
            AGENT_TOOL_ALLOWLIST,
            require_explicit_capabilities=True,
        )
        result, _record = gateway.invoke(
            agent_name=self.agent_name,
            tool=self.wrapped_tool,
            arguments=tool_input,
            context=self.runtime_context,
            call_args=args,
            call_kwargs=kwargs,
        )
        return result

    def __getattr__(self, name: str) -> Any:
        return getattr(self.wrapped_tool, name)


def assert_tool_allowed(agent_name: str, tool_name: str) -> None:
    allowed_tools = AGENT_TOOL_ALLOWLIST.get(agent_name)
    if allowed_tools is None or tool_name not in allowed_tools:
        raise ToolPermissionError(
            f"Agent '{agent_name}' is not allowed to call tool '{tool_name}'."
        )


def guard_tool(
    agent_name: str,
    tool: Any,
    *,
    runtime_context: Any | None = None,
) -> PermissionedTool:
    underlying_tool = getattr(tool, "wrapped_tool", tool)
    return PermissionedTool(
        agent_name=agent_name,
        wrapped_tool=underlying_tool,
        runtime_context=runtime_context,
    )


def guard_tools(
    agent_name: str,
    tools: Iterable[Any],
    *,
    runtime_context: Any | None = None,
) -> list[PermissionedTool]:
    return [
        guard_tool(agent_name, tool, runtime_context=runtime_context)
        for tool in tools
    ]


def tools_by_name(tools: Iterable[Any]) -> dict[str, Any]:
    return {tool.name: tool for tool in tools}


def get_allowed_tool_names(agent_name: str) -> set[str]:
    return set(AGENT_TOOL_ALLOWLIST[agent_name])


def validate_tool_set(agent_name: str, tools: Iterable[Any]) -> None:
    for tool in tools:
        assert_tool_allowed(agent_name, tool.name)


def tool_names(tool_mapping: Mapping[str, Any] | Iterable[Any]) -> list[str]:
    if isinstance(tool_mapping, Mapping):
        return sorted(tool_mapping)
    return sorted(tool.name for tool in tool_mapping)
