from fastapi import APIRouter, Depends, Header

from app.api.chat_response import build_chat_response
from app.core.chat_errors import log_public_exception, public_failure_result
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
        if request.expected_version is not None:
            call_kwargs["expected_version"] = request.expected_version
        if request.updated_arguments is not None:
            call_kwargs["updated_arguments"] = request.updated_arguments
        result = agent_dependency.confirm_pending_action(**call_kwargs)
    except Exception as exc:
        log_public_exception(
            "chat.confirmation_failed",
            exc,
            thread_id=request.thread_id,
            pending_action_id=request.pending_action_id,
        )
        result = public_failure_result(exc)
        result["pending_action_id"] = request.pending_action_id

    return build_chat_response(
        result,
        user_id=identity.effective_user_id,
        thread_id=request.thread_id,
        include_debug=request.include_debug,
        include_runtime_fields=any(
            key in result
            for key in ("retry_state", "runtime_error_code", "authoritative_run_id")
        ),
    )
