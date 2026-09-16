"""User preference repository functions backed by SQLAlchemy sessions."""

from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import UserPreference


ALLOWED_PREFERENCE_TYPES = {"budget", "brand", "avoid", "usage", "style", "other"}
MAX_PREFERENCE_COUNT = 50
MAX_PREFERENCE_TOTAL_CHARS = 8_000


def _normalize_preference_type(preference_type: str) -> tuple[str, bool]:
    normalized = preference_type.strip().lower()
    if normalized in ALLOWED_PREFERENCE_TYPES:
        return normalized, False
    return "other", True


def preference_to_dict(preference: UserPreference) -> dict[str, Any]:
    return {
        "id": preference.id,
        "user_id": preference.user_id,
        "preference_type": preference.preference_type,
        "preference_value": preference.preference_value,
        "created_at": preference.created_at,
        "updated_at": preference.updated_at,
    }


def get_user_preferences(
    session: Session,
    user_id: str,
    *,
    limit: int = MAX_PREFERENCE_COUNT,
    max_total_chars: int = MAX_PREFERENCE_TOTAL_CHARS,
) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), MAX_PREFERENCE_COUNT))
    max_total_chars = max(1, min(int(max_total_chars), MAX_PREFERENCE_TOTAL_CHARS))
    statement = (
        select(UserPreference)
        .where(UserPreference.user_id == user_id)
        .order_by(UserPreference.id.desc())
        .limit(limit)
    )
    results: list[dict[str, Any]] = []
    total_chars = 0
    for preference in session.scalars(statement).all():
        value = str(preference.preference_value or "").strip()
        if not value:
            continue
        remaining = max_total_chars - total_chars
        if remaining <= 0:
            break
        # Do not split one preference into a misleading fragment; keeping the
        # last complete records makes the character bound predictable.
        if len(value) > remaining:
            continue
        item = preference_to_dict(preference)
        item["preference_value"] = value
        item["source"] = "confirmed_user_preference"
        results.append(item)
        total_chars += len(value)
    return results


def add_user_preference(
    session: Session,
    user_id: str,
    preference_type: str,
    preference_value: str,
) -> dict[str, Any]:
    normalized_type, was_invalid_type = _normalize_preference_type(preference_type)
    preference = UserPreference(
        user_id=user_id,
        preference_type=normalized_type,
        preference_value=preference_value.strip(),
    )
    session.add(preference)
    session.flush()

    result = preference_to_dict(preference)
    result["was_invalid_type"] = was_invalid_type
    return result


def clear_user_preferences(session: Session, user_id: str) -> dict[str, Any]:
    result = session.execute(
        delete(UserPreference).where(UserPreference.user_id == user_id)
    )
    session.flush()
    return {"user_id": user_id, "deleted_count": result.rowcount or 0}
