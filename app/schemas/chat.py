from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field


STATUS_DESCRIPTION = (
    "Chat processing status. Stable public values are completed, "
    "confirmation_required, cancelled, and failed."
)
STATUS_EXAMPLES = ["completed", "confirmation_required", "cancelled", "failed"]


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
    status: str = Field(
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
    thread_id: Optional[str] = Field(
        default=None,
        description="Optional conversation/thread identifier echoed back to the caller.",
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
                    "user_id": "demo-user",
                    "pending_action_id": "pending-action-id",
                    "confirmed": True,
                    "thread_id": "demo-thread",
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
