"""ShopMind V1 user preference tools.

These tools store lightweight user preferences in the existing TechHub SQLite
database. They are intentionally independent from the Agent and API layers so
they can be tested and evolved separately.
"""

import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from config import DEFAULT_DB_PATH


ALLOWED_PREFERENCE_TYPES = {"budget", "brand", "avoid", "usage", "style", "other"}


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


def ensure_user_preferences_table() -> None:
    """Ensure the user_preferences table exists in the existing SQLite database."""
    with sqlite3.connect(DEFAULT_DB_PATH) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS user_preferences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                preference_type TEXT NOT NULL,
                preference_value TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.commit()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_preference_type(preference_type: str) -> tuple[str, bool]:
    normalized = preference_type.strip().lower()
    if normalized in ALLOWED_PREFERENCE_TYPES:
        return normalized, False
    return "other", True


def _fetch_user_preferences(user_id: str) -> List[Dict[str, Any]]:
    ensure_user_preferences_table()

    with sqlite3.connect(DEFAULT_DB_PATH) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT id, user_id, preference_type, preference_value, created_at, updated_at
            FROM user_preferences
            WHERE user_id = ?
            ORDER BY id ASC
            """,
            (user_id,),
        ).fetchall()

    return [dict(row) for row in rows]


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
    ensure_user_preferences_table()
    normalized_type, was_invalid_type = _normalize_preference_type(preference_type)
    now = _now_iso()

    with sqlite3.connect(DEFAULT_DB_PATH) as connection:
        connection.execute(
            """
            INSERT INTO user_preferences (
                user_id, preference_type, preference_value, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, normalized_type, preference_value.strip(), now, now),
        )
        connection.commit()

    type_message = f"偏好类型 {preference_type} 不在允许范围内，已归类为 other。" if was_invalid_type else f"偏好类型：{normalized_type}。"
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
    ensure_user_preferences_table()

    with sqlite3.connect(DEFAULT_DB_PATH) as connection:
        cursor = connection.execute(
            "DELETE FROM user_preferences WHERE user_id = ?",
            (user_id,),
        )
        connection.commit()
        deleted_count = cursor.rowcount

    return f"已清空用户 {user_id} 的购物偏好，共删除 {deleted_count} 条记录。"


__all__ = [
    "ALLOWED_PREFERENCE_TYPES",
    "ensure_user_preferences_table",
    "get_user_preferences",
    "add_user_preference",
    "clear_user_preferences",
]
