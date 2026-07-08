from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
import tools.preferences as preference_tools
from tools.preferences import (
    add_user_preference,
    clear_user_preferences,
    ensure_user_preferences_table,
    get_user_preferences,
)


TEST_USER_ID = "TEST_PREF_USER"


@pytest.fixture(autouse=True)
def preference_repository_session(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    @contextmanager
    def fake_preference_session():
        yield session

    monkeypatch.setattr(
        preference_tools, "_get_preference_session", fake_preference_session
    )
    yield
    session.close()


def test_ensure_user_preferences_table_is_compatibility_noop() -> None:
    assert ensure_user_preferences_table() is None


def test_get_user_preferences_returns_chinese_message_when_empty() -> None:
    result = get_user_preferences.invoke({"user_id": TEST_USER_ID})

    assert f"用户 {TEST_USER_ID} 暂无已记录的购物偏好" in result


def test_add_budget_preference_then_get_preferences() -> None:
    add_result = add_user_preference.invoke(
        {
            "user_id": TEST_USER_ID,
            "preference_type": "budget",
            "preference_value": "预算 1000 美元以内",
        }
    )
    get_result = get_user_preferences.invoke({"user_id": TEST_USER_ID})

    assert "已为用户 TEST_PREF_USER 记录购物偏好" in add_result
    assert "偏好类型：budget" in add_result
    assert "预算（budget）：预算 1000 美元以内" in get_result


def test_add_avoid_preference_then_get_preferences() -> None:
    add_user_preference.invoke(
        {
            "user_id": TEST_USER_ID,
            "preference_type": "avoid",
            "preference_value": "避免缺货商品",
        }
    )
    get_result = get_user_preferences.invoke({"user_id": TEST_USER_ID})

    assert "避免项（avoid）：避免缺货商品" in get_result


def test_clear_user_preferences_removes_only_target_user_preferences() -> None:
    other_user_id = "TEST_PREF_OTHER_USER"
    clear_user_preferences.invoke({"user_id": other_user_id})
    try:
        add_user_preference.invoke(
            {
                "user_id": TEST_USER_ID,
                "preference_type": "brand",
                "preference_value": "偏好 Apple",
            }
        )
        add_user_preference.invoke(
            {
                "user_id": other_user_id,
                "preference_type": "brand",
                "preference_value": "偏好 Dell",
            }
        )

        clear_result = clear_user_preferences.invoke({"user_id": TEST_USER_ID})
        target_result = get_user_preferences.invoke({"user_id": TEST_USER_ID})
        other_result = get_user_preferences.invoke({"user_id": other_user_id})

        assert "共删除 1 条记录" in clear_result
        assert f"用户 {TEST_USER_ID} 暂无已记录的购物偏好" in target_result
        assert "品牌（brand）：偏好 Dell" in other_result
    finally:
        clear_user_preferences.invoke({"user_id": other_user_id})


def test_invalid_preference_type_is_saved_as_other() -> None:
    add_result = add_user_preference.invoke(
        {
            "user_id": TEST_USER_ID,
            "preference_type": "color",
            "preference_value": "喜欢银色外观",
        }
    )
    get_result = get_user_preferences.invoke({"user_id": TEST_USER_ID})

    assert "偏好类型 color 不在允许范围内，已归类为 other" in add_result
    assert "其他（other）：喜欢银色外观" in get_result
