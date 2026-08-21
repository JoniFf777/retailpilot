"""Small, shared public error policy for Chat JSON, SSE, and confirmation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from app.core.logging import log_event, sanitize_error_message


PublicRetryState = Literal["none", "in_progress", "terminal"]

GENERIC_PUBLIC_ERROR_CODE = "runtime.internal_error"
GENERIC_PUBLIC_ERROR_MESSAGE = "请求暂时无法完成，请稍后重试。"

# Only codes with an established public/domain meaning may cross the Chat
# boundary. The message map is intentionally bounded: an arbitrary runtime
# or provider code is not allowed to become a public implementation detail.
_PUBLIC_ERROR_MESSAGES: dict[str, str] = {
    "runtime.internal_error": GENERIC_PUBLIC_ERROR_MESSAGE,
    "runtime.executor_exception": GENERIC_PUBLIC_ERROR_MESSAGE,
    "runtime.failed_result": "请求未能完成，请稍后重试。",
    "runtime.idempotency_in_progress": "相同请求仍在处理中，请稍后重试以恢复结果。",
    "runtime.idempotency_key_conflict": "幂等键已用于不同请求，无法重复使用。",
    "runtime.idempotency_record_invalid": "请求状态无效，请重新发起请求。",
    "runtime.idempotency_result_unavailable": "请求结果暂时不可用，请稍后重试。",
    "runtime.idempotency_owner_unavailable": "请求状态暂时不可用，请稍后重试。",
    "runtime.idempotency_persistence_failed": "请求状态暂时无法安全保存，请稍后重试。",
    "runtime.cancelled": "请求已停止。",
    "runtime.deadline_exceeded": "请求处理超时，请稍后重试。",
    "runtime.duration_budget_exceeded": "请求处理超时，请稍后重试。",
    "runtime.step_budget_exceeded": "请求处理未能在限定步骤内完成。",
    "runtime.tool_call_budget_exceeded": "请求调用资源已达上限，请稍后重试。",
    "runtime.usage_budget_unavailable": "请求资源暂时不可用，请稍后重试。",
    "runtime.usage_budget_exceeded": "请求资源已达上限，请稍后重试。",
    "tool.execution_failed": "工具暂时无法完成请求，请稍后重试。",
    "tool.output_limit_exceeded": "工具返回结果过大，无法安全处理。",
    "tool.cancelled": "工具请求已停止。",
    "tool.deadline_exceeded": "工具处理超时，请稍后重试。",
    "tool.run_duration_budget_exceeded": "工具处理超时，请稍后重试。",
    "agent.adapter_contract_failed": "Agent 返回结果暂时无法处理，请稍后重试。",
    "agent.transport_unavailable": "Agent 服务暂时不可用，请稍后重试。",
    "agent.transport_timeout": "Agent 服务处理超时，请稍后重试。",
    "agent.transport_protocol_error": "Agent 服务返回了无法处理的结果。",
    "plan.step_failed": "部分 Agent 步骤未能完成，请稍后重试。",
    "plan.step_budget_exceeded": "Agent 处理步骤已达上限。",
    "plan.deadline_exceeded": "Agent 处理超时，请稍后重试。",
    "plan.duration_budget_exceeded": "Agent 处理超时，请稍后重试。",
    "plan.usage_budget_unavailable": "Agent 资源暂时不可用，请稍后重试。",
    "plan.usage_budget_exceeded": "Agent 资源已达上限，请稍后重试。",
    "recommendation.validation_failed": "推荐结果暂时无法安全处理。",
    "recommendation_projection_corrupt": "已收到结果，但推荐信息暂时无法安全展示。",
    "pending_action_not_found": "待确认动作不存在或不属于当前用户/会话。",
    "recommendation_not_found": "推荐结果已不存在，请重新发起请求。",
    "sku_not_in_recommendation": "所选 SKU 不属于当前推荐结果。",
    "invalid_quantity": "商品数量无效，请重新输入。",
    "invalid_updated_fields": "待确认动作的修改内容无效。",
    "version_conflict": "待确认动作版本已变化，请重新加载后再确认。",
    "action_resolution_conflict": "待确认动作已被其他请求处理。",
    "action_expired": "待确认动作已过期，请重新发起请求。",
    "catalog_not_found": "商品或 SKU 已不存在，请重新选择。",
    "catalog_identifier_ambiguous": "商品标识存在冲突，请提供明确的 SKU。",
    "sku_ambiguous": "商品有多个规格，请先明确具体规格。",
    "catalog_identity_changed": "商品信息已变化，请重新发起请求。",
    "product_inactive": "商品当前不可售。",
    "sku_inactive": "SKU 当前不可售。",
    "insufficient_inventory": "当前库存不足，无法完成请求。",
    "cart_quantity_limit": "购物车数量超过限制。",
    "unsupported_action_schema": "该历史待确认动作已无法继续，请重新发起请求。",
    "invalid_action_payload": "待确认动作内容无效，请重新发起请求。",
    "expected_version_required": "待确认动作缺少有效版本，请重新加载后再试。",
}

PUBLIC_ERROR_CODES = frozenset(_PUBLIC_ERROR_MESSAGES)

_UNSAFE_DEBUG_KEY_PARTS = (
    "exception",
    "traceback",
    "stack",
    "sql",
    "driver",
    "filesystem",
    "path",
    "secret",
    "token",
    "password",
    "credential",
    "authorization",
    "cookie",
    "provider_payload",
    "raw_result",
)
_UNSAFE_DEBUG_KEYS = {
    "error",
    "error_message",
    "error_detail",
    "error_text",
    "exception_text",
    "traceback",
    "stack_trace",
}
_UNSAFE_DEBUG_VALUE_MARKERS = (
    "traceback (most recent call last)",
    "sqlalchemy.",
    "psycopg",
    "sqlite3.",
    "file \"",
    "bearer ",
    "api_key",
    "provider_payload",
)


@dataclass(frozen=True)
class PublicChatError:
    code: str
    message: str
    retry_state: PublicRetryState = "terminal"
    authoritative_run_id: str | None = None


def public_error(
    code: Any,
    *,
    retry_state: str = "terminal",
    authoritative_run_id: str | None = None,
) -> PublicChatError:
    """Return an allowlisted public error without trusting caller text."""

    normalized_code = str(code or "").strip()
    if normalized_code not in PUBLIC_ERROR_CODES:
        normalized_code = GENERIC_PUBLIC_ERROR_CODE
    normalized_retry_state: PublicRetryState = (
        "in_progress" if retry_state == "in_progress" or normalized_code == "runtime.idempotency_in_progress" else "terminal"
    )
    return PublicChatError(
        code=normalized_code,
        message=_PUBLIC_ERROR_MESSAGES[normalized_code],
        retry_state=normalized_retry_state,
        authoritative_run_id=authoritative_run_id,
    )


def public_error_from_exception(exc: BaseException) -> PublicChatError:
    """Map a typed exception or unknown exception to the public contract."""

    code = getattr(exc, "code", None) or getattr(exc, "error_code", None)
    return public_error(
        code,
        retry_state=(
            getattr(exc, "retry_state", "terminal")
            if isinstance(getattr(exc, "retry_state", "terminal"), str)
            else "terminal"
        ),
        authoritative_run_id=getattr(exc, "authoritative_run_id", None),
    )


def public_failure_result(
    error: PublicChatError | BaseException,
    *,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Build a safe legacy-shaped failure consumed by JSON and SSE routes."""

    projection = (
        error if isinstance(error, PublicChatError) else public_error_from_exception(error)
    )
    return {
        "answer": projection.message,
        "status": "failed",
        "tool_calls": [],
        "pending_action_id": None,
        "retry_state": projection.retry_state,
        "runtime_error_code": projection.code,
        "authoritative_run_id": projection.authoritative_run_id or run_id,
    }


def public_error_for_result(
    *,
    status: Any,
    code: Any,
    retry_state: str = "terminal",
    authoritative_run_id: str | None = None,
) -> PublicChatError | None:
    """Project a failed result; success answers are not rewritten here."""

    status_value = getattr(status, "value", status)
    if status_value != "failed":
        return None
    return public_error(
        code,
        retry_state=retry_state,
        authoritative_run_id=authoritative_run_id,
    )


def sanitize_public_debug(value: Any, *, _depth: int = 0) -> Any:
    """Keep known debug shapes bounded while removing internal diagnostics."""

    if _depth > 8:
        return None
    if isinstance(value, Mapping):
        output: dict[str, Any] = {}
        for raw_key, raw_value in value.items():
            key = str(raw_key)
            key_lower = key.lower()
            if key_lower in _UNSAFE_DEBUG_KEYS or any(
                part in key_lower for part in _UNSAFE_DEBUG_KEY_PARTS
            ):
                continue
            sanitized = sanitize_public_debug(raw_value, _depth=_depth + 1)
            if sanitized is not None:
                output[key] = sanitized
        return output
    if isinstance(value, (list, tuple)):
        return [
            sanitized
            for item in list(value)[:100]
            if (sanitized := sanitize_public_debug(item, _depth=_depth + 1)) is not None
        ]
    if isinstance(value, bool) or value is None or isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        normalized = sanitize_error_message(value, limit=512)
        lowered = normalized.lower()
        if any(marker in lowered for marker in _UNSAFE_DEBUG_VALUE_MARKERS):
            return None
        return normalized
    return None


def log_public_exception(
    event: str,
    exc: BaseException,
    *,
    code: str = GENERIC_PUBLIC_ERROR_CODE,
    run_id: str | None = None,
    trace_id: str | None = None,
    thread_id: str | None = None,
    pending_action_id: str | None = None,
) -> None:
    """Retain bounded internal diagnostics without making them public."""

    log_event(
        event,
        status="failed",
        error_code=code,
        error_class=type(exc).__name__,
        error_message=sanitize_error_message(exc),
        run_id=run_id,
        trace_id=trace_id,
        thread_id=thread_id,
        pending_action_id=pending_action_id,
    )


__all__ = [
    "GENERIC_PUBLIC_ERROR_CODE",
    "GENERIC_PUBLIC_ERROR_MESSAGE",
    "PUBLIC_ERROR_CODES",
    "PublicChatError",
    "log_public_exception",
    "public_error",
    "public_error_for_result",
    "public_error_from_exception",
    "public_failure_result",
    "sanitize_public_debug",
]
