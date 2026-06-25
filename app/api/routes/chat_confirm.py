from fastapi import APIRouter

from app.dependencies import agent as agent_dependency
from app.schemas.chat import ChatResponse, ConfirmChatRequest


router = APIRouter()


@router.post("/chat/confirm", response_model=ChatResponse)
async def confirm_chat(request: ConfirmChatRequest) -> ChatResponse:
    try:
        result = agent_dependency.confirm_pending_action(
            pending_action_id=request.pending_action_id,
            user_id=request.user_id,
            confirmed=request.confirmed,
        )
    except Exception as exc:
        result = {
            "answer": f"处理确认请求时发生错误：{exc}",
            "status": "failed",
            "tool_calls": [],
            "pending_action_id": request.pending_action_id,
        }

    return ChatResponse(
        answer=result.get("answer", ""),
        status=result.get("status", "completed"),
        tool_calls=result.get("tool_calls", []),
        user_id=request.user_id,
        thread_id=request.thread_id,
        pending_action_id=result.get("pending_action_id", request.pending_action_id),
    )
