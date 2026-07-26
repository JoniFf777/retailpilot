"""Centralized capability and pre-side-effect validation for runtime tools."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from .contracts import (
    DatabaseAccess,
    RunContext,
    ToolCallRecord,
    ToolResourcePolicy,
    ToolCallStatus,
    ToolSideEffectClass,
    utc_now,
)


class ToolGatewayError(PermissionError):
    """Raised before a tool call when the centralized policy rejects it."""


class ToolGatewayExecutionError(ToolGatewayError):
    """Raised after a tool attempt and retains its safe audit record."""

    def __init__(
        self,
        tool_call_record: ToolCallRecord,
        message: str = "Tool execution failed.",
    ) -> None:
        super().__init__(message)
        self.tool_call_record = tool_call_record


READ_PREFIXES = ("search_", "get_", "list_", "read_", "retrieve_", "compare_")
PREPARATION_TOOLS = {"prepare_add_to_cart", "prepare_save_preference"}
SENSITIVE_TOOLS = {
    "confirm_add_to_cart",
    "confirm_save_preference",
    "cancel_pending_action",
}
DATABASE_READ_TOOLS = {
    "search_products",
    "get_product_detail",
    "compare_products",
    "search_product_docs",
    "search_policy_docs",
    "get_user_preferences",
}
DATABASE_WRITE_TOOLS = PREPARATION_TOOLS | SENSITIVE_TOOLS


@dataclass(frozen=True)
class ToolCapability:
    name: str
    allowed_agents: frozenset[str]
    side_effect_class: ToolSideEffectClass = ToolSideEffectClass.NONE
    requires_confirmation: bool = False
    max_output_chars: int = 100_000
    max_duration_ms: int | None = None
    resource_policy: ToolResourcePolicy = field(default_factory=ToolResourcePolicy)


@dataclass(frozen=True)
class ToolCapabilityPolicy:
    """Static policy that must be declared for each production V3 tool."""

    allowed_agents: frozenset[str]
    side_effect_class: ToolSideEffectClass
    requires_confirmation: bool
    resource_policy: ToolResourcePolicy


def _database_read_policy(agent_name: str) -> ToolCapabilityPolicy:
    return ToolCapabilityPolicy(
        allowed_agents=frozenset({agent_name}),
        side_effect_class=ToolSideEffectClass.READ,
        requires_confirmation=False,
        resource_policy=ToolResourcePolicy(database_access=DatabaseAccess.READ),
    )


V3_TOOL_CAPABILITY_POLICIES: Mapping[str, ToolCapabilityPolicy] = MappingProxyType(
    {
        "search_products": _database_read_policy("product_agent"),
        "get_product_detail": _database_read_policy("product_agent"),
        "compare_products": _database_read_policy("product_agent"),
        "search_product_docs": _database_read_policy("rag_agent"),
        "search_policy_docs": _database_read_policy("rag_agent"),
        "get_user_preferences": _database_read_policy("preference_agent"),
        "prepare_add_to_cart": ToolCapabilityPolicy(
            allowed_agents=frozenset({"write_handoff"}),
            side_effect_class=ToolSideEffectClass.WRITE,
            requires_confirmation=True,
            resource_policy=ToolResourcePolicy(database_access=DatabaseAccess.WRITE),
        ),
        "prepare_save_preference": ToolCapabilityPolicy(
            allowed_agents=frozenset({"write_handoff"}),
            side_effect_class=ToolSideEffectClass.WRITE,
            requires_confirmation=True,
            resource_policy=ToolResourcePolicy(database_access=DatabaseAccess.WRITE),
        ),
        "confirm_add_to_cart": ToolCapabilityPolicy(
            allowed_agents=frozenset({"confirmation_boundary"}),
            side_effect_class=ToolSideEffectClass.SENSITIVE_WRITE,
            requires_confirmation=True,
            resource_policy=ToolResourcePolicy(database_access=DatabaseAccess.WRITE),
        ),
        "confirm_save_preference": ToolCapabilityPolicy(
            allowed_agents=frozenset({"confirmation_boundary"}),
            side_effect_class=ToolSideEffectClass.SENSITIVE_WRITE,
            requires_confirmation=True,
            resource_policy=ToolResourcePolicy(database_access=DatabaseAccess.WRITE),
        ),
        "cancel_pending_action": ToolCapabilityPolicy(
            allowed_agents=frozenset({"confirmation_boundary"}),
            side_effect_class=ToolSideEffectClass.SENSITIVE_WRITE,
            requires_confirmation=True,
            resource_policy=ToolResourcePolicy(database_access=DatabaseAccess.WRITE),
        ),
    }
)


def _side_effect_class(tool_name: str) -> ToolSideEffectClass:
    if tool_name in PREPARATION_TOOLS:
        return ToolSideEffectClass.WRITE
    if tool_name in SENSITIVE_TOOLS:
        return ToolSideEffectClass.SENSITIVE_WRITE
    if tool_name.lower().startswith(READ_PREFIXES):
        return ToolSideEffectClass.READ
    return ToolSideEffectClass.NONE


def _resource_policy(tool_name: str) -> ToolResourcePolicy:
    if tool_name in DATABASE_WRITE_TOOLS:
        return ToolResourcePolicy(database_access=DatabaseAccess.WRITE)
    if tool_name in DATABASE_READ_TOOLS:
        return ToolResourcePolicy(database_access=DatabaseAccess.READ)
    return ToolResourcePolicy()


class ToolGateway:
    """Registry that validates tool calls before delegating to a tool object."""

    def __init__(self, capabilities: Iterable[ToolCapability] = ()) -> None:
        self._capabilities: dict[str, ToolCapability] = {}
        for capability in capabilities:
            self.register(capability)

    @classmethod
    def from_allowlist(
        cls,
        allowlist: Mapping[str, Iterable[str]],
        *,
        require_explicit_capabilities: bool = False,
    ) -> "ToolGateway":
        tool_agents: dict[str, set[str]] = {}
        for agent_name, tool_names in allowlist.items():
            for tool_name in tool_names:
                tool_agents.setdefault(tool_name, set()).add(agent_name)
        capabilities = []
        for tool_name, agent_names in tool_agents.items():
            explicit_policy = V3_TOOL_CAPABILITY_POLICIES.get(tool_name)
            if explicit_policy is None and require_explicit_capabilities:
                raise ToolGatewayError(
                    f"Tool '{tool_name}' requires an explicit capability policy."
                )
            allowed_agents = frozenset(agent_names)
            if (
                require_explicit_capabilities
                and explicit_policy is not None
                and explicit_policy.allowed_agents != allowed_agents
            ):
                raise ToolGatewayError(
                    f"Tool '{tool_name}' agent assignment does not match its "
                    "explicit capability policy."
                )
            policy = explicit_policy or ToolCapabilityPolicy(
                allowed_agents=allowed_agents,
                side_effect_class=_side_effect_class(tool_name),
                requires_confirmation=(
                    tool_name in PREPARATION_TOOLS or tool_name in SENSITIVE_TOOLS
                ),
                resource_policy=_resource_policy(tool_name),
            )
            capabilities.append(
                ToolCapability(
                    name=tool_name,
                    allowed_agents=allowed_agents,
                    side_effect_class=policy.side_effect_class,
                    requires_confirmation=policy.requires_confirmation,
                    resource_policy=policy.resource_policy.model_copy(deep=True),
                )
            )
        return cls(capabilities)

    def register(self, capability: ToolCapability) -> None:
        if not capability.name.strip():
            raise ToolGatewayError("Tool capability name is required.")
        if capability.name in self._capabilities:
            raise ToolGatewayError(
                f"Tool capability '{capability.name}' is already registered."
            )
        self._validate_resource_policy(capability)
        self._capabilities[capability.name] = capability

    def capability_for(self, tool_name: str) -> ToolCapability:
        try:
            return self._capabilities[tool_name]
        except KeyError as exc:
            raise ToolGatewayError(f"Tool '{tool_name}' is not registered.") from exc

    def validate_invocation(
        self,
        *,
        agent_name: str,
        tool: Any,
        arguments: Any,
        context: RunContext | None = None,
    ) -> dict[str, Any]:
        tool_name = getattr(tool, "name", None)
        if not tool_name:
            raise ToolGatewayError("Tool is missing a stable name.")
        capability = self.capability_for(tool_name)
        if agent_name not in capability.allowed_agents:
            raise ToolGatewayError(
                f"Agent '{agent_name}' is not allowed to call tool '{tool_name}'."
            )
        if (
            context is not None
            and capability.side_effect_class == ToolSideEffectClass.SENSITIVE_WRITE
            and not context.policy.allow_sensitive_tools
        ):
            raise ToolGatewayError(
                f"Sensitive tool '{tool_name}' requires an approved runtime policy."
            )

        validated = self._validate_schema(tool, arguments)
        self._validate_ownership(validated, context)
        self._validate_budget(context)
        return validated

    def invoke(
        self,
        *,
        agent_name: str,
        tool: Any,
        arguments: Any,
        context: RunContext | None = None,
        call_args: tuple[Any, ...] = (),
        call_kwargs: Mapping[str, Any] | None = None,
    ) -> tuple[Any, ToolCallRecord]:
        validated = self.validate_invocation(
            agent_name=agent_name,
            tool=tool,
            arguments=arguments,
            context=context,
        )
        capability = self.capability_for(tool.name)
        audit_sequence = self._reserve_tool_call(context)
        record = ToolCallRecord(
            tool_name=tool.name,
            caller=agent_name,
            capability=capability.name,
            argument_hash=self._argument_hash(validated),
            side_effect_class=capability.side_effect_class,
            requires_confirmation=capability.requires_confirmation,
            resource_policy=capability.resource_policy,
            audit_sequence=audit_sequence,
        )
        self._check_execution_controls(context, record)
        try:
            result = tool.invoke(
                validated,
                *call_args,
                **dict(call_kwargs or {}),
            )
        except Exception as exc:
            failed_record = self._complete_record(
                record,
                status=ToolCallStatus.FAILED,
                result_metadata={
                    "error_code": "tool.execution_failed",
                    "exception_type": exc.__class__.__name__,
                },
            )
            failed_record = self._with_duration_audit(capability, failed_record)
            self._store_record(context, failed_record)
            raise ToolGatewayExecutionError(failed_record) from exc

        record = self._complete_record(record, status=ToolCallStatus.COMPLETED)
        record = self._with_duration_audit(capability, record)
        if len(str(result)) > capability.max_output_chars:
            failed_record = record.model_copy(
                update={
                    "status": ToolCallStatus.FAILED,
                    "result_metadata": {
                        **record.result_metadata,
                        "error_code": "tool.output_limit_exceeded",
                    },
                }
            )
            self._store_record(context, failed_record)
            raise ToolGatewayExecutionError(
                failed_record,
                f"Tool '{tool.name}' exceeded its output limit.",
            )
        self._store_record(context, record)
        return result, record

    def _check_execution_controls(
        self,
        context: RunContext | None,
        record: ToolCallRecord,
    ) -> None:
        if context is None:
            return
        if context.cancellation_requested:
            skipped_record = self._complete_record(
                record,
                status=ToolCallStatus.SKIPPED,
                result_metadata={
                    "error_code": "tool.cancelled",
                    "run_id": context.run_id,
                },
            )
            self._store_record(context, skipped_record)
            raise ToolGatewayExecutionError(
                skipped_record,
                f"Tool '{record.tool_name}' skipped because the run was cancelled.",
            )

        now = utc_now()
        deadline = context.request.deadline_at or context.budget.deadline_at
        if deadline is not None and self._as_utc(deadline) <= now:
            skipped_record = self._complete_record(
                record,
                status=ToolCallStatus.SKIPPED,
                result_metadata={
                    "error_code": "tool.deadline_exceeded",
                    "deadline_at": self._as_utc(deadline).isoformat(),
                },
            )
            self._store_record(context, skipped_record)
            raise ToolGatewayExecutionError(
                skipped_record,
                f"Tool '{record.tool_name}' skipped because the run deadline elapsed.",
            )

        if context.budget.max_duration_ms is None:
            return
        elapsed_ms = (now - self._as_utc(context.started_at)).total_seconds() * 1000
        if elapsed_ms < context.budget.max_duration_ms:
            return
        skipped_record = self._complete_record(
            record,
            status=ToolCallStatus.SKIPPED,
            result_metadata={
                "error_code": "tool.run_duration_budget_exceeded",
                "max_duration_ms": context.budget.max_duration_ms,
            },
        )
        self._store_record(context, skipped_record)
        raise ToolGatewayExecutionError(
            skipped_record,
            f"Tool '{record.tool_name}' skipped because the run duration budget elapsed.",
        )

    @staticmethod
    def _complete_record(
        record: ToolCallRecord,
        *,
        status: ToolCallStatus,
        result_metadata: dict[str, Any] | None = None,
    ) -> ToolCallRecord:
        completed_at = utc_now()
        return record.model_copy(
            update={
                "status": status,
                "completed_at": completed_at,
                "duration_ms": max(
                    0,
                    int((completed_at - record.started_at).total_seconds() * 1000),
                ),
                "result_metadata": result_metadata or {},
            }
        )

    @staticmethod
    def _with_duration_audit(
        capability: ToolCapability,
        record: ToolCallRecord,
    ) -> ToolCallRecord:
        if capability.max_duration_ms is None:
            return record
        duration_ms = record.duration_ms
        metadata = {
            **record.result_metadata,
            "duration_limit_ms": capability.max_duration_ms,
            "duration_limit_exceeded": (
                duration_ms is not None and duration_ms > capability.max_duration_ms
            ),
        }
        return record.model_copy(update={"result_metadata": metadata})

    @staticmethod
    def _store_record(context: RunContext | None, record: ToolCallRecord) -> None:
        if context is None:
            return
        with context.locked_metadata() as metadata:
            records = metadata.setdefault("tool_call_records", [])
            if isinstance(records, list):
                records.append(record.model_dump(mode="json"))
                records.sort(
                    key=lambda item: int(item.get("audit_sequence") or 0)
                    if isinstance(item, dict)
                    else 0
                )

    @staticmethod
    def _validate_schema(tool: Any, arguments: Any) -> dict[str, Any]:
        schema = getattr(tool, "args_schema", None)
        if schema is None:
            if isinstance(arguments, dict):
                return dict(arguments)
            raise ToolGatewayError("Tool arguments must be an object.")
        try:
            model = schema.model_validate(arguments)
        except AttributeError:
            model = schema.parse_obj(arguments)
        except Exception as exc:
            raise ToolGatewayError(
                f"Invalid arguments for tool '{tool.name}'."
            ) from exc
        return model.model_dump(mode="python")

    @staticmethod
    def _validate_ownership(
        arguments: dict[str, Any],
        context: RunContext | None,
    ) -> None:
        if context is None:
            return
        argument_user_id = arguments.get("user_id")
        if (
            argument_user_id is not None
            and context.user_id is not None
            and argument_user_id != context.user_id
        ):
            raise ToolGatewayError("Tool user_id does not match the runtime user.")
        argument_thread_id = arguments.get("thread_id")
        if (
            argument_thread_id is not None
            and context.client_thread_id is not None
            and argument_thread_id != context.client_thread_id
        ):
            raise ToolGatewayError("Tool thread_id does not match the runtime thread.")

    @staticmethod
    def _validate_budget(context: RunContext | None) -> None:
        if context is None or context.budget.max_tool_calls is None:
            return
        with context.locked_metadata() as metadata:
            current_count = int(metadata.get("tool_gateway_call_count", 0))
        if current_count >= context.budget.max_tool_calls:
            raise ToolGatewayError("Runtime tool-call budget has been exceeded.")

    @staticmethod
    def _reserve_tool_call(context: RunContext | None) -> int | None:
        if context is None:
            return None
        with context.locked_metadata() as metadata:
            current_count = int(metadata.get("tool_gateway_call_count", 0))
            max_tool_calls = context.budget.max_tool_calls
            if max_tool_calls is not None and current_count >= max_tool_calls:
                raise ToolGatewayError("Runtime tool-call budget has been exceeded.")
            audit_sequence = current_count + 1
            metadata["tool_gateway_call_count"] = audit_sequence
            return audit_sequence

    @staticmethod
    def _validate_resource_policy(capability: ToolCapability) -> None:
        database_access = capability.resource_policy.database_access
        if (
            database_access == DatabaseAccess.READ
            and capability.side_effect_class != ToolSideEffectClass.READ
        ):
            raise ToolGatewayError(
                "Database read capabilities must use the read side-effect class."
            )
        if (
            database_access == DatabaseAccess.WRITE
            and capability.side_effect_class
            not in {ToolSideEffectClass.WRITE, ToolSideEffectClass.SENSITIVE_WRITE}
        ):
            raise ToolGatewayError(
                "Database write capabilities must use a write side-effect class."
            )
        if (
            capability.side_effect_class == ToolSideEffectClass.SENSITIVE_WRITE
            and not capability.requires_confirmation
        ):
            raise ToolGatewayError(
                "Sensitive write capabilities must require confirmation."
            )
        if (
            capability.requires_confirmation
            and capability.side_effect_class
            not in {ToolSideEffectClass.WRITE, ToolSideEffectClass.SENSITIVE_WRITE}
        ):
            raise ToolGatewayError(
                "Confirmation requirements are only valid for write capabilities."
            )

    @staticmethod
    def _argument_hash(arguments: dict[str, Any]) -> str:
        encoded = json.dumps(arguments, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
