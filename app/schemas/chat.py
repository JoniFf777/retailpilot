from typing import Any, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.recommendation import RecommendationResult
from app.schemas.pending_actions import RecommendationContextView


STATUS_DESCRIPTION = (
    "Chat processing status. Stable public values are completed, "
    "confirmation_required, cancelled, and failed."
)
STATUS_EXAMPLES = ["completed", "confirmation_required", "cancelled", "failed"]
ChatStatus = Literal["completed", "confirmation_required", "cancelled", "failed"]
RetryState = Literal["none", "in_progress", "terminal"]
ProjectionErrorCode = Literal["recommendation_projection_corrupt"]


class ProjectionError(BaseModel):
    """Safe public projection failure for a completed persisted run."""

    code: ProjectionErrorCode
    message: str


class ChatRequest(BaseModel):
    message: str = Field(
        ...,
        min_length=1,
        description=(
            "User message sent to the chat API. V3 write handoff supports "
            "explicit product IDs such as TECH-KEY-010 and same-thread "
            "candidate selection such as 1."
        ),
        examples=["add to cart TECH-KEY-010 quantity 2"],
    )
    user_id: Optional[str] = Field(
        default=None,
        description=(
            "Optional user identifier. Required when a write handoff creates "
            "or confirms a pending action."
        ),
        examples=["demo-user"],
    )
    thread_id: Optional[str] = Field(
        default=None,
        description=(
            "Optional conversation/thread identifier. Recommended for "
            "same-thread candidate selection context."
        ),
        examples=["demo-thread"],
    )
    include_debug: bool = Field(
        default=False,
        description="Return optional debug metadata for evaluation and troubleshooting.",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "message": "add to cart TECH-KEY-010 quantity 2",
                    "user_id": "demo-user",
                    "thread_id": "demo-thread",
                    "include_debug": True,
                },
                {
                    "message": "1",
                    "user_id": "demo-user",
                    "thread_id": "demo-thread",
                    "include_debug": True,
                },
            ]
        }
    )


class ChatResponse(BaseModel):
    answer: str = Field(..., description="Assistant answer returned by the backend.")
    status: ChatStatus = Field(
        default="completed",
        description=STATUS_DESCRIPTION,
        examples=STATUS_EXAMPLES,
    )
    tool_calls: List[str] = Field(
        default_factory=list,
        description=(
            "Names of tools called by the ShopMind Agent, for example "
            "prepare_add_to_cart, confirm_add_to_cart, or cancel_pending_action."
        ),
        examples=[["prepare_add_to_cart"]],
    )
    user_id: Optional[str] = Field(
        default=None,
        description="User identifier echoed back to the caller when provided.",
        examples=["demo-user"],
    )
    thread_id: Optional[str] = Field(
        default=None,
        description="Conversation/thread identifier echoed back to the caller when provided.",
        examples=["demo-thread"],
    )
    pending_action_id: Optional[str] = Field(
        default=None,
        description="Pending action identifier when user confirmation is required.",
        examples=["pending-action-id"],
    )
    recommendation: RecommendationResult | None = Field(
        default=None,
        description="Structured catalog recommendation when the Recommendation Gate handled the request.",
    )
    recommendation_context: RecommendationContextView | None = Field(
        default=None,
        description="Stable source run identifier for creating a recommendation-backed action.",
    )
    projection_error: ProjectionError | None = Field(
        default=None,
        description="Stable public projection error for a corrupt persisted recommendation; run state is unchanged.",
    )
    retry_state: RetryState = Field(
        default="none",
        description="Machine-readable transport/retry state. In-progress is recoverable and is not terminal failure.",
    )
    runtime_error_code: str | None = Field(
        default=None,
        description="Machine-readable runtime error code when a retry/recovery state is present.",
    )
    authoritative_run_id: str | None = Field(
        default=None,
        description="Winner Run identity for an in-progress idempotency recovery response.",
    )
    run_id: Optional[str] = Field(
        default=None,
        description=(
            "Opaque persisted run identifier returned only when "
            "include_debug=true."
        ),
        examples=["runtime-run-id"],
    )
    trace_id: Optional[str] = Field(
        default=None,
        description=(
            "Opaque trace identifier returned only when include_debug=true."
        ),
        examples=["runtime-trace-id"],
    )
    debug: Optional[dict[str, Any]] = Field(
        default=None,
        description=(
            "Optional structured debug metadata when requested. V3 handoff "
            "debug may include multi_agent_handoff, write_handoff_debug, "
            "candidate_context events, and confirmation events."
        ),
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "answer": "Pending add-to-cart action created.",
                    "status": "confirmation_required",
                    "tool_calls": ["prepare_add_to_cart"],
                    "user_id": "demo-user",
                    "thread_id": "demo-thread",
                    "pending_action_id": "pending-action-id",
                    "run_id": "runtime-run-id",
                    "trace_id": "runtime-trace-id",
                    "debug": {
                        "multi_agent_handoff": {
                            "from": "multi_agent_read_path",
                            "to": "v3_write_handoff_path",
                            "reason": "read_only_multi_agent_write_intent",
                            "status": "confirmation_required",
                        }
                    },
                }
            ]
        }
    )


class ConfirmChatRequest(BaseModel):
    user_id: str = Field(
        ...,
        min_length=1,
        description="User identifier for the pending action.",
        examples=["demo-user"],
    )
    pending_action_id: str = Field(
        ...,
        min_length=1,
        description="Pending action identifier to confirm or cancel.",
        examples=["pending-action-id"],
    )
    confirmed: bool = Field(
        ...,
        description="Whether the user confirmed the pending action.",
        examples=[True],
    )
    expected_version: Optional[int] = Field(
        default=None,
        ge=1,
        description=(
            "Client-held PendingAction version. Required when confirming or "
            "cancelling a canonical SKU add-to-cart action."
        ),
        examples=[1],
    )
    thread_id: Optional[str] = Field(
        default=None,
        description="Optional conversation/thread identifier echoed back to the caller.",
        examples=["demo-thread"],
    )
    updated_arguments: Optional[dict[str, Any]] = Field(
        default=None,
        description=(
            "Optional server-validated edits applied atomically before confirmation. "
            "Editable fields depend on the persisted action type."
        ),
        examples=[{"quantity": 2}],
    )
    include_debug: bool = Field(
        default=False,
        description="Return optional debug metadata for evaluation and troubleshooting.",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "user_id": "demo-user",
                    "pending_action_id": "pending-action-id",
                    "confirmed": True,
                    "thread_id": "demo-thread",
                    "updated_arguments": {"quantity": 2},
                    "include_debug": True,
                },
                {
                    "user_id": "demo-user",
                    "pending_action_id": "pending-action-id",
                    "confirmed": False,
                    "thread_id": "demo-thread",
                    "include_debug": True,
                },
            ]
        }
    )
