"""ShopMind user preference tools.

These tools store lightweight user preferences through the V2 repository layer
and return Chinese, LLM-readable responses for the ShopMind Agent.
"""

from contextlib import contextmanager
from typing import Any, Dict, List

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app.repositories import preferences as preference_repository


ALLOWED_PREFERENCE_TYPES = preference_repository.ALLOWED_PREFERENCE_TYPES


class GetUserPreferencesInput(BaseModel):
    user_id: str = Field(..., min_length=1, description="用户 ID，用于读取该用户已记录的购物偏好。")


class AddUserPreferenceInput(BaseModel):
    user_id: str = Field(..., min_length=1, description="用户 ID，用于保存该用户的购物偏好。")
    preference_type: str = Field(
        ...,
        min_length=1,
        description="偏好类型。允许 budget、brand、avoid、usage、style、other；其他类型会自动归为 other。",
    )
    preference_value: str = Field(..., min_length=1, description="偏好内容，例如预算 1000 美元以内、偏好 Apple、避免缺货商品。")


class ClearUserPreferencesInput(BaseModel):
    user_id: str = Field(..., min_length=1, description="用户 ID，用于清空该用户的全部偏好记录。")


@contextmanager
def _get_preference_session():
    from app.db.session import SessionLocal

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def ensure_user_preferences_table() -> None:
    """Compatibility shim; V2 schema is managed by Alembic migrations."""
    return None


def _normalize_preference_type(preference_type: str) -> tuple[str, bool]:
    return preference_repository._normalize_preference_type(preference_type)


def _fetch_user_preferences(user_id: str) -> List[Dict[str, Any]]:
    with _get_preference_session() as session:
        return preference_repository.get_user_preferences(session, user_id)


def _format_preference_type(preference_type: str) -> str:
    labels = {
        "budget": "预算",
        "brand": "品牌",
        "avoid": "避免项",
        "usage": "用途",
        "style": "风格",
        "other": "其他",
    }
    return labels.get(preference_type, "其他")


@tool(args_schema=GetUserPreferencesInput)
def get_user_preferences(user_id: str) -> str:
    """读取用户购物偏好，适合在需要个性化推荐、确认预算、品牌偏好、用途或避免项时调用。

    输入字段含义：
    - user_id：用户 ID，用于查询该用户已保存的偏好。

    返回内容：
    - 如果存在偏好，返回中文格式化的偏好列表；
    - 如果没有偏好，返回中文提示，说明当前用户尚未记录偏好。
    """
    preferences = _fetch_user_preferences(user_id)

    if not preferences:
        return f"用户 {user_id} 暂无已记录的购物偏好。"

    lines = [f"用户 {user_id} 的购物偏好："]
    for index, preference in enumerate(preferences, 1):
        type_label = _format_preference_type(preference["preference_type"])
        lines.append(
            f"{index}. {type_label}（{preference['preference_type']}）：{preference['preference_value']}"
        )

    return "\n".join(lines)


@tool(args_schema=AddUserPreferenceInput)
def add_user_preference(user_id: str, preference_type: str, preference_value: str) -> str:
    """新增一条用户购物偏好，适合在用户明确表达预算、品牌偏好、用途、风格或需要避免的商品特征时调用。

    输入字段含义：
    - user_id：用户 ID；
    - preference_type：偏好类型，允许 budget、brand、avoid、usage、style、other；
    - preference_value：偏好内容，例如“预算 1000 美元以内”“偏好 Apple”“避免缺货商品”。

    返回内容：
    - 返回中文成功提示；
    - 如果 preference_type 不在允许范围内，会自动归为 other，并在返回中明确说明。
    """
    with _get_preference_session() as session:
        try:
            preference = preference_repository.add_user_preference(
                session,
                user_id=user_id,
                preference_type=preference_type,
                preference_value=preference_value,
            )
            session.commit()
        except Exception:
            session.rollback()
            raise

    type_message = (
        f"偏好类型 {preference_type} 不在允许范围内，已归类为 other。"
        if preference["was_invalid_type"]
        else f"偏好类型：{preference['preference_type']}。"
    )
    return (
        f"已为用户 {user_id} 记录购物偏好：{preference_value.strip()}。\n"
        f"{type_message}"
    )


@tool(args_schema=ClearUserPreferencesInput)
def clear_user_preferences(user_id: str) -> str:
    """清空指定用户的购物偏好，主要适合测试或用户明确要求清除偏好记忆时调用。

    输入字段含义：
    - user_id：用户 ID。

    返回内容：
    - 返回中文清理结果，说明删除了多少条偏好记录。
    """
    with _get_preference_session() as session:
        try:
            result = preference_repository.clear_user_preferences(session, user_id)
            session.commit()
        except Exception:
            session.rollback()
            raise

    return f"已清空用户 {user_id} 的购物偏好，共删除 {result['deleted_count']} 条记录。"


__all__ = [
    "ALLOWED_PREFERENCE_TYPES",
    "ensure_user_preferences_table",
    "get_user_preferences",
    "add_user_preference",
    "clear_user_preferences",
]
