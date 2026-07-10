from typing import Any, List, Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="User message sent to the chat API.")
    user_id: Optional[str] = Field(
        default=None,
        description="Optional user identifier for future personalization.",
    )
    thread_id: Optional[str] = Field(
        default=None,
        description="Optional conversation/thread identifier for future Agent memory.",
    )
    include_debug: bool = Field(
        default=False,
        description="Return optional debug metadata for evaluation and troubleshooting.",
    )


class ChatResponse(BaseModel):
    answer: str = Field(..., description="Assistant answer returned by the backend.")
    status: str = Field(
        default="completed",
        description="Chat processing status. V1 supports completed, confirmation_required, cancelled, or failed.",
    )
    tool_calls: List[str] = Field(
        default_factory=list,
        description="Names of tools called by the ShopMind Agent.",
    )
    user_id: Optional[str] = Field(
        default=None,
        description="User identifier echoed back to the caller when provided.",
    )
    thread_id: Optional[str] = Field(
        default=None,
        description="Conversation/thread identifier echoed back to the caller when provided.",
    )
    pending_action_id: Optional[str] = Field(
        default=None,
        description="Pending action identifier when user confirmation is required.",
    )
    debug: Optional[dict[str, Any]] = Field(
        default=None,
        description="Optional structured debug metadata when requested.",
    )


class ConfirmChatRequest(BaseModel):
    user_id: str = Field(..., min_length=1, description="User identifier for the pending action.")
    pending_action_id: str = Field(..., min_length=1, description="Pending action identifier to confirm or cancel.")
    confirmed: bool = Field(..., description="Whether the user confirmed the pending action.")
    thread_id: Optional[str] = Field(
        default=None,
        description="Optional conversation/thread identifier echoed back to the caller.",
    )
    include_debug: bool = Field(
        default=False,
        description="Return optional debug metadata for evaluation and troubleshooting.",
    )
