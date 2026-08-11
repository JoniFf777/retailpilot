from fastapi import APIRouter, Depends, Header

from app.dependencies import agent as agent_dependency
from app.dependencies.security import bind_request_user, get_identity_boundary
from app.api.chat_response import build_chat_response
from app.security import AuditRequestOperation, IdentityBoundary
from app.schemas.chat import ChatRequest, ChatResponse


router = APIRouter()


@router.post("/chat", response_model=ChatResponse, response_model_exclude_unset=True)
async def chat(
    request: ChatRequest,
    identity_boundary: IdentityBoundary = Depends(get_identity_boundary),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> ChatResponse:
    identity = bind_request_user(
        identity_boundary,
        request.user_id,
        require_user=False,
        request_operation=AuditRequestOperation.CHAT,
    )
    call_kwargs = {
        "message": request.message,
        "user_id": identity.effective_user_id,
        "thread_id": request.thread_id,
    }
    if idempotency_key:
        call_kwargs["idempotency_key"] = idempotency_key
    result = agent_dependency.call_shopmind_agent(**call_kwargs)

    return build_chat_response(
        result,
        user_id=identity.effective_user_id,
        thread_id=request.thread_id,
        include_debug=request.include_debug,
    )
