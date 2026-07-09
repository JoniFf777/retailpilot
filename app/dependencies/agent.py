"""FastAPI dependency helpers for ShopMind Agent access."""

from typing import Any, Optional

from agents.shopmind_multi_agent import (
    create_supervisor_router,
    invoke_shopmind_multi_agent,
)
from agents.shopmind_agent import invoke_shopmind_agent
from app.core.settings import get_settings
from tools.cart import cancel_pending_action, confirm_add_to_cart


def call_shopmind_agent(
    message: str,
    user_id: Optional[str] = None,
    thread_id: Optional[str] = None,
) -> dict[str, Any]:
    """Call the ShopMind Agent behind the API boundary.

    This thin wrapper keeps route handlers simple and gives tests a stable
    monkeypatch target so API tests do not need to call a real LLM.
    """
    settings = get_settings()
    if settings.shopmind_agent_mode == "multi":
        return invoke_shopmind_multi_agent(
            message=message,
            user_id=user_id,
            thread_id=thread_id,
            supervisor_router=create_supervisor_router(
                getattr(settings, "shopmind_supervisor_router", "deterministic")
            ),
        )

    return invoke_shopmind_agent(message=message, user_id=user_id)


def confirm_pending_action(
    pending_action_id: str,
    user_id: str,
    confirmed: bool,
) -> dict[str, Any]:
    """Confirm or cancel a pending action behind the API boundary."""
    if confirmed:
        answer = confirm_add_to_cart.invoke(
            {"pending_action_id": pending_action_id, "user_id": user_id}
        )
        return {
            "answer": answer,
            "status": "completed" if answer.startswith("已确认") else "failed",
            "tool_calls": ["confirm_add_to_cart"],
            "pending_action_id": pending_action_id,
        }

    answer = cancel_pending_action.invoke(
        {"pending_action_id": pending_action_id, "user_id": user_id}
    )
    return {
        "answer": answer,
        "status": "cancelled" if answer.startswith("已取消") else "failed",
        "tool_calls": ["cancel_pending_action"],
        "pending_action_id": pending_action_id,
    }
