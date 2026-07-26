from fastapi import APIRouter, Depends, Header

from app.dependencies import agent as agent_dependency
from app.dependencies.security import bind_request_user, get_identity_boundary
from app.security import AuditRequestOperation, IdentityBoundary
from app.schemas.chat import ChatResponse, ConfirmChatRequest


router = APIRouter()


@router.post(
    "/chat/confirm",
    response_model=ChatResponse,
    response_model_exclude_unset=True,
)
async def confirm_chat(
    request: ConfirmChatRequest,
    identity_boundary: IdentityBoundary = Depends(get_identity_boundary),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> ChatResponse:
    identity = bind_request_user(
        identity_boundary,
        request.user_id,
        require_user=True,
        request_operation=AuditRequestOperation.CONFIRM_PENDING_ACTION,
    )
    try:
        call_kwargs = {
            "pending_action_id": request.pending_action_id,
            "user_id": identity.effective_user_id,
            "confirmed": request.confirmed,
            "thread_id": request.thread_id,
        }
        if idempotency_key:
            call_kwargs["idempotency_key"] = idempotency_key
        if request.updated_arguments is not None:
            call_kwargs["updated_arguments"] = request.updated_arguments
        result = agent_dependency.confirm_pending_action(**call_kwargs)
    except Exception as exc:
        result = {
            "answer": f"处理确认请求时发生错误：{exc}",
            "status": "failed",
            "tool_calls": [],
            "pending_action_id": request.pending_action_id,
        }

    response_kwargs = {}
    if request.include_debug:
        if result.get("debug") is not None:
            response_kwargs["debug"] = result["debug"]
        if result.get("run_id") is not None:
            response_kwargs["run_id"] = result["run_id"]
        if result.get("trace_id") is not None:
            response_kwargs["trace_id"] = result["trace_id"]

    return ChatResponse(
        answer=result.get("answer", ""),
        status=result.get("status", "completed"),
        tool_calls=result.get("tool_calls", []),
        user_id=identity.effective_user_id,
        thread_id=request.thread_id,
        pending_action_id=result.get("pending_action_id", request.pending_action_id),
        **response_kwargs,
    )
