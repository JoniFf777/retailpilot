"""FastAPI dependency helpers for ShopMind Agent access."""

from typing import Any, Optional

from agents.shopmind_multi_agent import (
    create_supervisor_router,
    invoke_shopmind_multi_agent,
)
from agents.shopmind_multi_agent.write_handoff import invoke_write_handoff
from agents.shopmind_agent import invoke_shopmind_agent
from app.core.settings import get_settings
from tools.cart import cancel_pending_action, confirm_add_to_cart


WRITE_PATH_HANDOFF_ANSWER_TYPE = "write_path_handoff"


def _extract_multi_agent_decision(result: dict[str, Any]) -> dict[str, Any]:
    raw_result = result.get("raw_result")
    if isinstance(raw_result, dict) and isinstance(raw_result.get("decision"), dict):
        return raw_result["decision"]

    debug = result.get("debug")
    if isinstance(debug, dict) and isinstance(debug.get("decision"), dict):
        return debug["decision"]

    return {}


def _requires_write_handoff(result: dict[str, Any]) -> bool:
    decision = _extract_multi_agent_decision(result)
    return decision.get("answer_type") == WRITE_PATH_HANDOFF_ANSWER_TYPE


def _attach_multi_agent_handoff_debug(
    handoff_result: dict[str, Any],
    multi_agent_result: dict[str, Any],
) -> dict[str, Any]:
    result = dict(handoff_result)
    multi_debug = multi_agent_result.get("debug")
    if not isinstance(multi_debug, dict):
        return result

    decision = _extract_multi_agent_decision(multi_agent_result)
    result["debug"] = {
        "multi_agent_handoff": {
            "from": "multi_agent_read_path",
            "to": "v3_write_handoff_path",
            "reason": decision.get("followup_reason"),
            "status": handoff_result.get("status"),
        },
        "multi_agent_debug": multi_debug,
    }
    handoff_debug = handoff_result.get("debug")
    if isinstance(handoff_debug, dict):
        result["debug"]["write_handoff_debug"] = handoff_debug
    return result


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
        multi_agent_result = invoke_shopmind_multi_agent(
            message=message,
            user_id=user_id,
            thread_id=thread_id,
            supervisor_router=create_supervisor_router(
                getattr(settings, "shopmind_supervisor_router", "deterministic"),
                model=getattr(settings, "workshop_model", None),
            ),
        )
        if _requires_write_handoff(multi_agent_result):
            handoff_result = invoke_write_handoff(
                message=message,
                user_id=user_id,
                thread_id=thread_id,
            )
            return _attach_multi_agent_handoff_debug(
                handoff_result,
                multi_agent_result,
            )

        return multi_agent_result

    return invoke_shopmind_agent(message=message, user_id=user_id, thread_id=thread_id)


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
