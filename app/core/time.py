"""Small timezone normalization helpers for database/API boundaries."""

from __future__ import annotations

from datetime import datetime, timezone


def ensure_utc(value: datetime) -> datetime:
    """Treat SQLite's timezone-stripped values as UTC at the boundary."""

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


__all__ = ["ensure_utc"]
