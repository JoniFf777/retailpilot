"""User preference repository functions backed by SQLAlchemy sessions."""

from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import UserPreference


ALLOWED_PREFERENCE_TYPES = {"budget", "brand", "avoid", "usage", "style", "other"}


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


def get_user_preferences(session: Session, user_id: str) -> list[dict[str, Any]]:
    statement = (
        select(UserPreference)
        .where(UserPreference.user_id == user_id)
        .order_by(UserPreference.id.asc())
    )
    return [
        preference_to_dict(preference)
        for preference in session.scalars(statement).all()
    ]


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
