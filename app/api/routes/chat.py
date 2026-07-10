from fastapi import APIRouter

from app.dependencies import agent as agent_dependency
from app.schemas.chat import ChatRequest, ChatResponse


router = APIRouter()


@router.post("/chat", response_model=ChatResponse, response_model_exclude_unset=True)
async def chat(request: ChatRequest) -> ChatResponse:
    result = agent_dependency.call_shopmind_agent(
        message=request.message,
        user_id=request.user_id,
        thread_id=request.thread_id,
    )

    response_kwargs = {}
    if request.include_debug and result.get("debug") is not None:
        response_kwargs["debug"] = result["debug"]

    return ChatResponse(
        answer=result.get("answer", ""),
        status=result.get("status", "completed"),
        tool_calls=result.get("tool_calls", []),
        user_id=request.user_id,
        thread_id=request.thread_id,
        pending_action_id=result.get("pending_action_id"),
        **response_kwargs,
    )
