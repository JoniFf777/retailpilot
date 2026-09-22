"""Closed task lifecycle transitions used by API and worker code."""

from __future__ import annotations

from .contracts import TaskStatus


class InvalidTaskTransition(ValueError):
    pass


TERMINAL = frozenset({"succeeded", "failed", "cancelled", "expired"})


def transition_task(task, target: TaskStatus) -> None:
    current = task.status
    allowed = {
        "queued": {"running", "cancelled", "expired", "failed"},
        "running": {"queued", "waiting_input", "awaiting_approval", "succeeded", "failed", "cancelled", "expired"},
        "waiting_input": {"queued", "cancelled", "expired"},
        "awaiting_approval": {"queued", "succeeded", "cancelled", "expired"},
        "succeeded": set(), "failed": set(), "cancelled": set(), "expired": set(),
    }
    if target not in allowed.get(current, set()):
        raise InvalidTaskTransition(f"{current}_to_{target}_forbidden")
    task.status = target
    task.version += 1


__all__ = ["InvalidTaskTransition", "TERMINAL", "transition_task"]
