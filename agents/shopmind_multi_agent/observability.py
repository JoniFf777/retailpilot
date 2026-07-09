"""Lightweight execution trace helpers for the ShopMind multi-agent graph."""

from typing import Any

from .state import ShopMindMultiAgentState


def append_agent_step(
    state: ShopMindMultiAgentState,
    *,
    node: str,
    event: str,
    **metadata: Any,
) -> list[dict[str, Any]]:
    steps = list(state.get("agent_steps", []))
    clean_metadata = {
        key: value
        for key, value in metadata.items()
        if value is not None
    }
    steps.append(
        {
            "index": len(steps) + 1,
            "node": node,
            "event": event,
            **clean_metadata,
        }
    )
    return steps
