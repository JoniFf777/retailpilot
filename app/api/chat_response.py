"""One public projection boundary shared by Chat JSON and SSE terminal results."""

from __future__ import annotations

import logging
from typing import Any

from app.core.chat_errors import (
    public_error_for_result,
    sanitize_public_debug,
)
from app.runtime import RunResult
from app.schemas.chat import ChatResponse
from app.schemas.recommendation import RecommendationResult


PROJECTION_CORRUPTION_CODE = "recommendation_projection_corrupt"
_audit_logger = logging.getLogger("shopmind.audit")


def build_chat_response(
    result: RunResult | dict[str, Any],
    *,
    user_id: str | None,
    thread_id: str | None,
    include_debug: bool,
    include_runtime_fields: bool = True,
) -> ChatResponse:
    """Read and validate public data without changing a completed persisted run."""

    if isinstance(result, RunResult):
        runtime_error_code = result.metadata.get("runtime_error_code")
        if result.error is not None:
            runtime_error_code = result.error.code
        payload = {
            "answer": result.answer,
            "status": result.status,
            "tool_calls": result.tool_calls,
            "pending_action_id": result.pending_action_id,
            "run_id": result.run_id,
            "trace_id": result.trace_id,
            "debug": result.debug,
            "recommendation": result.output_data.get("recommendation"),
            "retry_state": result.metadata.get("retry_state", "terminal"),
            "runtime_error_code": runtime_error_code,
            "authoritative_run_id": result.metadata.get("authoritative_run_id"),
        }
    else:
        payload = dict(result)

    status = payload.get("status", "completed")
    retry_state = payload.get("retry_state", "none")
    runtime_error_code = payload.get("runtime_error_code")
    authoritative_run_id = payload.get("authoritative_run_id")
    public_failure = public_error_for_result(
        status=status,
        code=runtime_error_code,
        retry_state=retry_state,
        authoritative_run_id=authoritative_run_id,
    )
    response: dict[str, Any] = {
        "answer": public_failure.message if public_failure else payload.get("answer", ""),
        "status": status,
        "tool_calls": payload.get("tool_calls", []),
        "pending_action_id": payload.get("pending_action_id"),
        "user_id": user_id,
        "thread_id": thread_id,
    }
    if include_runtime_fields:
        response.update(
            {
                "retry_state": public_failure.retry_state if public_failure else retry_state,
                "runtime_error_code": public_failure.code if public_failure else runtime_error_code,
                "authoritative_run_id": (
                    public_failure.authoritative_run_id
                    if public_failure
                    else authoritative_run_id
                ),
            }
        )
    recommendation = payload.get("recommendation")
    if recommendation is not None:
        try:
            response["recommendation"] = RecommendationResult.model_validate(recommendation)
            if payload.get("run_id"):
                response["recommendation_context"] = {
                    "source_run_id": str(payload["run_id"]),
                }
        except Exception:
            _audit_logger.warning(
                "recommendation_projection_corrupt",
                extra={
                    "event": PROJECTION_CORRUPTION_CODE,
                    "run_id": payload.get("run_id"),
                    "trace_id": payload.get("trace_id"),
                },
            )
            response["projection_error"] = {
                "code": PROJECTION_CORRUPTION_CODE,
                "message": "The persisted recommendation could not be projected safely.",
            }
    if include_debug:
        if payload.get("debug") is not None:
            safe_debug = sanitize_public_debug(payload["debug"])
            if safe_debug:
                response["debug"] = safe_debug
        if payload.get("run_id") is not None:
            response["run_id"] = payload["run_id"]
        if payload.get("trace_id") is not None:
            response["trace_id"] = payload["trace_id"]
    return ChatResponse.model_validate(response)
