"""Lightweight execution trace helpers for the ShopMind multi-agent graph."""

from typing import Any

from .state import ShopMindMultiAgentState


def _clean_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in metadata.items()
        if value is not None
    }


def append_agent_step(
    state: ShopMindMultiAgentState,
    *,
    node: str,
    event: str,
    **metadata: Any,
) -> list[dict[str, Any]]:
    steps = list(state.get("agent_steps", []))
    clean_metadata = _clean_metadata(metadata)
    steps.append(
        {
            "index": len(steps) + 1,
            "node": node,
            "event": event,
            **clean_metadata,
        }
    )
    return steps


def append_candidate_context_event(
    events: list[dict[str, Any]] | None,
    *,
    event: str,
    **metadata: Any,
) -> list[dict[str, Any]]:
    """Append stable write-handoff candidate-context observability metadata."""

    context_events = list(events or [])
    context_events.append(
        {
            "index": len(context_events) + 1,
            "event": event,
            **_clean_metadata(metadata),
        }
    )
    return context_events


def build_candidate_context_debug(
    events: list[dict[str, Any]],
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    return {"candidate_context": {"events": events}}


def append_confirmation_event(
    events: list[dict[str, Any]] | None,
    *,
    event: str,
    **metadata: Any,
) -> list[dict[str, Any]]:
    """Append stable pending-action confirmation observability metadata."""

    confirmation_events = list(events or [])
    confirmation_events.append(
        {
            "index": len(confirmation_events) + 1,
            "event": event,
            **_clean_metadata(metadata),
        }
    )
    return confirmation_events


def build_confirmation_debug(
    events: list[dict[str, Any]],
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    return {"confirmation": {"events": events}}
