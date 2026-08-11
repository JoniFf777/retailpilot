"""One public projection boundary shared by Chat JSON and SSE terminal results."""

from __future__ import annotations

import logging
from typing import Any

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
) -> ChatResponse:
    """Read and validate public data without changing a completed persisted run."""

    if isinstance(result, RunResult):
        payload = {
            "answer": result.answer,
            "status": result.status,
            "tool_calls": result.tool_calls,
            "pending_action_id": result.pending_action_id,
            "run_id": result.run_id,
            "trace_id": result.trace_id,
            "debug": result.debug,
            "recommendation": result.output_data.get("recommendation"),
        }
    else:
        payload = dict(result)

    response: dict[str, Any] = {
        "answer": payload.get("answer", ""),
        "status": payload.get("status", "completed"),
        "tool_calls": payload.get("tool_calls", []),
        "pending_action_id": payload.get("pending_action_id"),
        "user_id": user_id,
        "thread_id": thread_id,
    }
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
            response["debug"] = payload["debug"]
        if payload.get("run_id") is not None:
            response["run_id"] = payload["run_id"]
        if payload.get("trace_id") is not None:
            response["trace_id"] = payload["trace_id"]
    return ChatResponse.model_validate(response)
