"""FastAPI dependency helpers for ShopMind Agent access."""

import inspect
from typing import Any, Optional
from collections.abc import Callable

from agents.shopmind_multi_agent import (
    create_agent_planner,
    create_supervisor_router,
    invoke_shopmind_multi_agent,
)
from agents.shopmind_multi_agent.observability import (
    append_confirmation_event,
    build_confirmation_debug,
)
from agents.shopmind_multi_agent.write_handoff import (
    invoke_write_handoff,
    is_preference_write_intent,
)
from agents.shopmind_agent import invoke_shopmind_agent
from app.core.settings import get_settings
from app.runtime import (
    ACTION_REGISTRY,
    ActionRegistryError,
    ActionRequest,
    ActionTransitionRequest,
    AgentEvent,
    CancellationCheck,
    EventSink,
    EventVisibility,
    RunMode,
    RunOperation,
    RunRequest,
    RunResult,
    ShopMindRuntimeHarness,
    ToolGateway,
    build_runtime_budget,
    build_runtime_policy,
    run_result_to_legacy_response,
)
from agents.shopmind_multi_agent.permissions import AGENT_TOOL_ALLOWLIST
from app.schemas.pending_actions import CartActionOutcome
from tools.cart import (
    cancel_pending_action,
    confirm_add_to_cart,
    confirm_save_preference,
    format_cart_action_outcome,
    format_preference_action_outcome,
    resolve_pending_action,
)


WRITE_PATH_HANDOFF_ANSWER_TYPE = "write_path_handoff"
runtime_harness = ShopMindRuntimeHarness()
tool_gateway = ToolGateway.from_allowlist(
    AGENT_TOOL_ALLOWLIST,
    require_explicit_capabilities=True,
)


def _extract_multi_agent_decision(result: dict[str, Any]) -> dict[str, Any]:
    raw_result = result.get("raw_result")
    if isinstance(raw_result, dict) and isinstance(raw_result.get("decision"), dict):
        return raw_result["decision"]

    debug = result.get("debug")
    if isinstance(debug, dict) and isinstance(debug.get("decision"), dict):
        return debug["decision"]

    return {}


def _requires_write_handoff(result: dict[str, Any]) -> bool:
    decision = _extract_multi_agent_decision(result)
    return decision.get("answer_type") == WRITE_PATH_HANDOFF_ANSWER_TYPE


def _invoke_multi_agent_with_context(
    *,
    message: str,
    user_id: str | None,
    thread_id: str | None,
    supervisor_router: Any,
    agent_planner: Any,
    runtime_context: Any,
) -> dict[str, Any]:
    """Pass runtime context while keeping test/legacy callable adapters compatible."""

    kwargs: dict[str, Any] = {
        "message": message,
        "user_id": user_id,
        "thread_id": thread_id,
        "supervisor_router": supervisor_router,
    }
    try:
        parameters = inspect.signature(invoke_shopmind_multi_agent).parameters
    except (TypeError, ValueError):
        parameters = {}
    accepts_context = "runtime_context" in parameters or any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in parameters.values()
    )
    if accepts_context:
        kwargs["runtime_context"] = runtime_context
    accepts_planner = "agent_planner" in parameters or any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in parameters.values()
    )
    if accepts_planner:
        kwargs["agent_planner"] = agent_planner
    return invoke_shopmind_multi_agent(**kwargs)


def _invoke_write_handoff_with_context(
    *,
    message: str,
    user_id: str | None,
    thread_id: str | None,
    runtime_context: Any,
) -> dict[str, Any]:
    """Keep legacy write-handoff test and plugin callables compatible."""

    kwargs: dict[str, Any] = {
        "message": message,
        "user_id": user_id,
        "thread_id": thread_id,
    }
    try:
        parameters = inspect.signature(invoke_write_handoff).parameters
    except (TypeError, ValueError):
        parameters = {}
    accepts_kwargs = any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in parameters.values()
    )
    if accepts_kwargs or "runtime_context" in parameters:
        kwargs["runtime_context"] = runtime_context
    if accepts_kwargs or "tool_gateway" in parameters:
        kwargs["tool_gateway"] = tool_gateway
    return invoke_write_handoff(**kwargs)


def _tool_answer_failed(answer: str) -> bool:
    lowered = answer.lower()
    return answer.startswith("鏃犳硶") or "error" in lowered or "failed" in lowered


def _parse_cart_action_outcome(answer: Any) -> CartActionOutcome | None:
    if not isinstance(answer, str):
        return None
    try:
        return CartActionOutcome.model_validate_json(answer)
    except (TypeError, ValueError):
        return None


def _attach_multi_agent_handoff_debug(
    handoff_result: dict[str, Any],
    multi_agent_result: dict[str, Any],
) -> dict[str, Any]:
    result = dict(handoff_result)
    multi_debug = multi_agent_result.get("debug")
    if not isinstance(multi_debug, dict):
        return result

    decision = _extract_multi_agent_decision(multi_agent_result)
    result["debug"] = {
        "multi_agent_handoff": {
            "from": "multi_agent_read_path",
            "to": "v3_write_handoff_path",
            "reason": decision.get("followup_reason"),
            "status": handoff_result.get("status"),
        },
        "multi_agent_debug": multi_debug,
    }
    handoff_debug = handoff_result.get("debug")
    if isinstance(handoff_debug, dict):
        result["debug"]["write_handoff_debug"] = handoff_debug
    return result


def execute_shopmind_agent_run(
    message: str,
    user_id: Optional[str] = None,
    thread_id: Optional[str] = None,
    *,
    idempotency_key: str | None = None,
    event_sink: EventSink | None = None,
    cancellation_check: CancellationCheck | None = None,
) -> RunResult:
    """Execute one run and return the canonical runtime result.

    This thin wrapper keeps route handlers simple and gives tests a stable
    monkeypatch target so API tests do not need to call a real LLM.
    """

    settings = get_settings()
    operation = RunOperation.CHAT
    request = RunRequest(
        operation=operation,
        user_id=user_id,
        thread_id=thread_id,
        input_text=message,
        idempotency_key=idempotency_key,
        mode=(
            RunMode.MULTI if settings.shopmind_agent_mode == "multi" else RunMode.SINGLE
        ),
        policy=build_runtime_policy(settings, operation),
        budget=build_runtime_budget(settings),
        metadata={
            "governance_audit_enabled": bool(
                getattr(settings, "shopmind_governance_audit_enabled", False)
            ),
        },
    )

    def executor(context) -> dict[str, Any]:
        if settings.shopmind_agent_mode == "multi":
            multi_agent_result = _invoke_multi_agent_with_context(
                message=message,
                user_id=user_id,
                thread_id=thread_id,
                supervisor_router=create_supervisor_router(
                    getattr(settings, "shopmind_supervisor_router", "deterministic"),
                    model=getattr(settings, "workshop_model", None),
                ),
                agent_planner=create_agent_planner(
                    getattr(settings, "shopmind_agent_planner", "deterministic"),
                    model=getattr(settings, "workshop_model", None),
                ),
                runtime_context=context,
            )
            if _requires_write_handoff(multi_agent_result):
                handoff_result = _invoke_write_handoff_with_context(
                    message=message,
                    user_id=user_id,
                    thread_id=thread_id,
                    runtime_context=context,
                )
                return _attach_multi_agent_handoff_debug(
                    handoff_result,
                    multi_agent_result,
                )

            return multi_agent_result

        if is_preference_write_intent(message):
            return _invoke_write_handoff_with_context(
                message=message,
                user_id=user_id,
                thread_id=thread_id,
                runtime_context=context,
            )
        return invoke_shopmind_agent(
            message=message,
            user_id=user_id,
            thread_id=thread_id,
        )

    return runtime_harness.run(
        request,
        executor,
        event_sink=event_sink,
        cancellation_check=cancellation_check,
    )


def call_shopmind_agent(
    message: str,
    user_id: Optional[str] = None,
    thread_id: Optional[str] = None,
    *,
    idempotency_key: str | None = None,
    event_sink: EventSink | None = None,
    cancellation_check: CancellationCheck | None = None,
) -> dict[str, Any]:
    """Backward-compatible dict facade over :func:`execute_shopmind_agent_run`."""

    result = execute_shopmind_agent_run(
        message,
        user_id,
        thread_id,
        idempotency_key=idempotency_key,
        event_sink=event_sink,
        cancellation_check=cancellation_check,
    )
    return run_result_to_legacy_response(result, include_debug=True)


def confirm_pending_action(
    pending_action_id: str,
    user_id: str,
    confirmed: bool,
    thread_id: Optional[str] = None,
    *,
    idempotency_key: str | None = None,
    event_sink: EventSink | None = None,
    updated_arguments: dict[str, Any] | None = None,
    expected_version: int | None = None,
) -> dict[str, Any]:
    """Confirm or cancel a pending action behind the API boundary."""

    settings = get_settings()
    operation = RunOperation.CONFIRM_PENDING_ACTION
    request = RunRequest(
        operation=operation,
        user_id=user_id,
        input_data={
            "pending_action_id": pending_action_id,
            "confirmed": confirmed,
            "thread_id": thread_id,
            **(
                {"expected_version": expected_version}
                if expected_version is not None
                else {}
            ),
            **(
                {"updated_arguments": updated_arguments}
                if updated_arguments is not None
                else {}
            ),
        },
        idempotency_key=idempotency_key,
        mode=(
            RunMode.MULTI if settings.shopmind_agent_mode == "multi" else RunMode.SINGLE
        ),
        policy=build_runtime_policy(settings, operation),
        budget=build_runtime_budget(settings),
        metadata={
            "governance_audit_enabled": bool(
                getattr(settings, "shopmind_governance_audit_enabled", False)
            ),
        },
    )
    def executor(context) -> dict[str, Any]:
        resolved = resolve_pending_action(
            pending_action_id=pending_action_id,
            user_id=user_id,
            thread_id=thread_id,
        )
        if resolved.get("status") != "resolved":
            context.emit_event(
                "action.failed",
                visibility=EventVisibility.CLIENT,
                agent_name="confirmation_boundary",
                payload={
                    "action_id": pending_action_id,
                    "status": "failed",
                    "reason": "unresolved_or_scope_denied",
                },
            )
            return {
                "answer": "无法处理待确认动作：动作不存在或不属于当前用户/会话。",
                "status": "failed",
                "tool_calls": [],
                "pending_action_id": pending_action_id,
                "runtime_error_code": "pending_action_not_found",
            }
        action_type = str(resolved.get("action_type") or "")
        context.emit_event(
            "action.resumed",
            visibility=EventVisibility.CLIENT,
            agent_name="confirmation_boundary",
            payload={
                "action_id": pending_action_id,
                "action_type": action_type,
                "status": str(resolved.get("action_status") or "pending"),
                "resume_token": "persisted_action_id",
            },
        )
        validated_updated_arguments: dict[str, Any] | None = None
        if updated_arguments is not None:
            try:
                if not confirmed:
                    raise ActionRegistryError(
                        "Action edits are only accepted with confirmation."
                    )
                validated_updated_arguments = (
                    ACTION_REGISTRY.validate_updated_arguments(
                        action_type,
                        updated_arguments,
                    )
                )
            except ActionRegistryError:
                context.emit_event(
                    "action.failed",
                    visibility=EventVisibility.CLIENT,
                    agent_name="confirmation_boundary",
                    payload={
                        "action_id": pending_action_id,
                        "action_type": action_type,
                        "status": "failed",
                        "reason": "invalid_edit",
                    },
                )
                return {
                    "answer": "Action edit payload is invalid for this pending action.",
                    "status": "failed",
                    "tool_calls": [],
                    "pending_action_id": pending_action_id,
                    "runtime_error_code": "invalid_updated_fields",
                }
        transition_request = ActionTransitionRequest(
            action_type=action_type,
            action_id=pending_action_id,
            user_id=user_id,
            thread_id=thread_id,
            confirmed=confirmed,
            updated_arguments=validated_updated_arguments,
        )
        try:
            ACTION_REGISTRY.validate_transition(transition_request)
        except Exception:
            context.emit_event(
                "action.failed",
                visibility=EventVisibility.CLIENT,
                agent_name="confirmation_boundary",
                payload={
                    "action_id": pending_action_id,
                    "status": "failed",
                    "reason": "unregistered_action",
                },
            )
            return {
                "answer": "无法处理待确认动作：动作类型未注册。",
                "status": "failed",
                "tool_calls": [],
                "pending_action_id": pending_action_id,
                "runtime_error_code": "unsupported_action_schema",
            }
        tool_call = ACTION_REGISTRY.transition_tool(transition_request)
        if (
            tool_call == "cancel_pending_action"
            and action_type in {"add_to_cart", "save_preference"}
            and expected_version is None
        ):
            context.emit_event(
                "action.failed",
                visibility=EventVisibility.CLIENT,
                agent_name="confirmation_boundary",
                payload={
                    "action_id": pending_action_id,
                    "action_type": action_type,
                    "status": "failed",
                    "reason": "expected_version_required",
                },
            )
            return {
                "answer": "待确认动作缺少客户端版本，请重新加载后再取消。",
                "status": "failed",
                "tool_calls": [],
                "pending_action_id": pending_action_id,
                "runtime_error_code": "expected_version_required",
            }
        transition_tools = {
            "confirm_add_to_cart": confirm_add_to_cart,
            "confirm_save_preference": confirm_save_preference,
            "cancel_pending_action": cancel_pending_action,
        }
        transition_tool = transition_tools.get(tool_call)
        if transition_tool is None:
            context.emit_event(
                "action.failed",
                visibility=EventVisibility.CLIENT,
                agent_name="confirmation_boundary",
                payload={
                    "action_id": pending_action_id,
                    "action_type": action_type,
                    "status": "failed",
                    "reason": "handler_unavailable",
                },
            )
            return {
                "answer": "无法处理待确认动作：未配置安全处理器。",
                "status": "failed",
                "tool_calls": [],
                "pending_action_id": pending_action_id,
                "runtime_error_code": "runtime.internal_error",
            }
        try:
            answer, tool_record = tool_gateway.invoke(
                agent_name="confirmation_boundary",
                tool=transition_tool,
                arguments={
                    "pending_action_id": pending_action_id,
                    "user_id": user_id,
                    "thread_id": thread_id,
                    **(
                        {"expected_version": expected_version}
                        if tool_call in {
                            "confirm_add_to_cart",
                            "confirm_save_preference",
                            "cancel_pending_action",
                        }
                        else {}
                    ),
                    **(
                        {"updated_arguments": validated_updated_arguments}
                        if confirmed and validated_updated_arguments is not None
                        else {}
                    ),
                },
                context=context,
            )
        except Exception:
            context.emit_event(
                "action.failed",
                visibility=EventVisibility.CLIENT,
                agent_name="confirmation_boundary",
                payload={
                    "action_id": pending_action_id,
                    "action_type": action_type,
                    "status": "failed",
                    "reason": "handler_failed",
                },
            )
            raise

        if confirmed:
            typed_outcome = (
                _parse_cart_action_outcome(answer)
                if action_type in {"add_to_cart", "save_preference"}
                else None
            )
            if action_type == "add_to_cart":
                if typed_outcome is None:
                    status = "failed"
                    answer = "无法处理加购动作：确认边界未收到有效的 typed outcome。"
                    outcome_code = "invalid_action_payload"
                else:
                    status = "completed" if typed_outcome.status == "confirmed" else "failed"
                    answer = format_cart_action_outcome(typed_outcome)
                    outcome_code = typed_outcome.code
                lifecycle = (
                    "expired"
                    if outcome_code == "action_expired"
                    else ("confirmed" if status == "completed" else "failed")
                )
            elif action_type == "save_preference":
                if typed_outcome is None:
                    status = "failed"
                    answer = "无法处理保存偏好动作：确认边界未收到有效的 typed outcome。"
                    outcome_code = "invalid_action_payload"
                else:
                    status = "completed" if typed_outcome.status == "confirmed" else "failed"
                    answer = format_preference_action_outcome(typed_outcome)
                    outcome_code = typed_outcome.code
                lifecycle = (
                    "expired"
                    if outcome_code == "action_expired"
                    else ("confirmed" if status == "completed" else "failed")
                )
            else:
                status = "failed" if _tool_answer_failed(answer) else "completed"
                outcome_code = None
                lifecycle = (
                    "expired"
                    if "expired" in answer.lower() or "过期" in answer
                    else ("confirmed" if status == "completed" else "failed")
                )
            if status == "completed" and validated_updated_arguments is not None:
                context.emit_event(
                    "action.edited",
                    visibility=EventVisibility.CLIENT,
                    agent_name="confirmation_boundary",
                    payload={
                        "action_id": pending_action_id,
                        "action_type": action_type,
                        "status": "edited",
                        "updated_fields": sorted(validated_updated_arguments),
                    },
                )
            context.emit_event(
                f"action.{lifecycle}",
                visibility=EventVisibility.CLIENT,
                agent_name="confirmation_boundary",
                payload={
                    "action_id": pending_action_id,
                    "action_type": action_type,
                    "status": lifecycle,
                    "tool_call": tool_call,
                },
            )
            event = (
                "pending_action_confirmed"
                if status == "completed"
                else "pending_action_failed"
            )
            return {
                "answer": answer,
                "status": status,
                "tool_calls": [tool_call],
                "tool_call_records": [tool_record.model_dump(mode="json")],
                "pending_action_id": pending_action_id,
                "runtime_error_code": outcome_code if status == "failed" else None,
                "debug": build_confirmation_debug(
                    append_confirmation_event(
                        None,
                        event=event,
                        requested_confirmation=True,
                        status=status,
                        tool_call=tool_call,
                        **({"action_type": action_type} if action_type != "add_to_cart" else {}),
                    )
                ),
            }

        typed_cancel = (
            _parse_cart_action_outcome(answer)
            if action_type in {"add_to_cart", "save_preference"}
            else None
        )
        if typed_cancel is not None:
            status = "cancelled" if typed_cancel.status == "cancelled" else "failed"
            outcome_code = typed_cancel.code
            answer = (
                format_preference_action_outcome(typed_cancel)
                if action_type == "save_preference"
                else format_cart_action_outcome(typed_cancel)
            )
        else:
            status = "failed" if _tool_answer_failed(answer) else "cancelled"
            outcome_code = None
        lifecycle = (
            "expired"
            if outcome_code == "action_expired"
            or "expired" in answer.lower()
            or "过期" in answer
            else ("cancelled" if status == "cancelled" else "failed")
        )
        context.emit_event(
            f"action.{lifecycle}",
            visibility=EventVisibility.CLIENT,
            agent_name="confirmation_boundary",
            payload={
                "action_id": pending_action_id,
                "action_type": action_type,
                "status": lifecycle,
                "tool_call": tool_call,
            },
        )
        event = (
            "pending_action_cancelled"
            if status == "cancelled"
            else "pending_action_failed"
        )
        return {
            "answer": answer,
            "status": status,
            "tool_calls": [tool_call],
            "tool_call_records": [tool_record.model_dump(mode="json")],
            "pending_action_id": pending_action_id,
            "runtime_error_code": outcome_code if status == "failed" else None,
            "debug": build_confirmation_debug(
                append_confirmation_event(
                    None,
                    event=event,
                    requested_confirmation=False,
                    status=status,
                    tool_call=tool_call,
                    **({"action_type": action_type} if action_type != "add_to_cart" else {}),
                )
            ),
        }

    result = runtime_harness.run(request, executor, event_sink=event_sink)
    return run_result_to_legacy_response(result, include_debug=True)
