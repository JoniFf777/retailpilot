"""Focused Agent write-boundary and canonical preference HITL tests."""

from contextlib import contextmanager
import json

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from types import SimpleNamespace

import tools.cart as cart_tools
from app.dependencies import agent as agent_dependency
from agents.shopmind_agent import SHOPMIND_TOOLS
from agents.shopmind_multi_agent.permissions import AGENT_TOOL_ALLOWLIST
from agents.shopmind_multi_agent.preference_agent import PREFERENCE_AGENT_TOOLS
from app.db.base import Base
from app.db.models import PendingAction, UserPreference
from app.repositories import preferences as preference_repository


@pytest.fixture
def preference_session(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    session = factory()

    @contextmanager
    def fake_session():
        yield session

    monkeypatch.setattr(cart_tools, "_get_cart_session", fake_session)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _prepare() -> dict:
    return json.loads(
        cart_tools.prepare_save_preference.invoke(
            {
                "user_id": "hitl-user",
                "thread_id": "hitl-thread",
                "preference_type": "avoid",
                "preference_value": "高噪声键盘",
            }
        )
    )


def test_active_agent_tools_have_no_direct_domain_preference_writer() -> None:
    single_names = {tool.name for tool in SHOPMIND_TOOLS}
    preference_names = {tool.name for tool in PREFERENCE_AGENT_TOOLS}

    assert "add_user_preference" not in single_names
    assert "clear_user_preferences" not in single_names
    assert preference_names == {"get_user_preferences"}
    assert "add_user_preference" not in AGENT_TOOL_ALLOWLIST["write_handoff"]
    assert "confirm_save_preference" not in AGENT_TOOL_ALLOWLIST["write_handoff"]
    assert "clear_user_preferences" not in AGENT_TOOL_ALLOWLIST["confirmation_boundary"]


def test_single_agent_preference_intent_uses_shared_write_handoff(monkeypatch) -> None:
    calls: list[tuple[str, str | None, str | None]] = []

    class FakeHarness:
        def run(self, request, executor, **_kwargs):
            assert request.mode == "single"
            return executor(object())

    def fake_handoff(*, message, user_id, thread_id, runtime_context):
        calls.append((message, user_id, thread_id))
        assert runtime_context is not None
        return {
            "answer": "已生成待确认的保存偏好动作。",
            "status": "confirmation_required",
            "tool_calls": ["prepare_save_preference"],
            "pending_action_id": "single-preference-action",
        }

    monkeypatch.setattr(
        agent_dependency,
        "get_settings",
        lambda: SimpleNamespace(shopmind_agent_mode="single", shopmind_agent_task_max_attempts=1),
    )
    monkeypatch.setattr(agent_dependency, "runtime_harness", FakeHarness())
    monkeypatch.setattr(agent_dependency, "invoke_write_handoff", fake_handoff)
    monkeypatch.setattr(
        agent_dependency,
        "invoke_shopmind_agent",
        lambda **_kwargs: pytest.fail("Single Agent must not execute a direct preference writer"),
    )

    result = agent_dependency.execute_shopmind_agent_run(
        "记住我喜欢安静键盘",
        user_id="single-user",
        thread_id="single-thread",
    )

    assert result["status"] == "confirmation_required"
    assert calls == [("记住我喜欢安静键盘", "single-user", "single-thread")]


def test_prepare_preference_is_canonical_and_does_not_write(preference_session: Session) -> None:
    outcome = _prepare()

    assert outcome["status"] == "prepared"
    action = preference_session.get(PendingAction, outcome["pending_action_id"])
    assert action is not None
    assert action.payload_json == {
        "schema_version": "shopmind.pending_action.save_preference.v1",
        "operation": "add",
        "preference_type": "avoid",
        "preference_value": "高噪声键盘",
    }
    assert action.user_id == "hitl-user"
    assert action.thread_id == "hitl-thread"
    assert action.version == 1
    assert preference_session.scalar(
        select(UserPreference).where(UserPreference.user_id == "hitl-user")
    ) is None


def test_confirm_writes_once_and_replay_does_not_duplicate(preference_session: Session) -> None:
    prepared = _prepare()
    args = {
        "pending_action_id": prepared["pending_action_id"],
        "user_id": "hitl-user",
        "thread_id": "hitl-thread",
        "expected_version": 1,
    }

    confirmed = json.loads(cart_tools.confirm_save_preference.invoke(args))
    replay = json.loads(cart_tools.confirm_save_preference.invoke(args))

    assert confirmed["status"] == "confirmed"
    assert replay["status"] == "confirmed"
    assert replay["idempotent_replay"] is True
    assert preference_session.query(UserPreference).count() == 1


def test_missing_version_owner_mismatch_and_cancel_do_not_write(preference_session: Session) -> None:
    prepared = _prepare()
    pending_id = prepared["pending_action_id"]

    missing_version = json.loads(
        cart_tools.confirm_save_preference.invoke(
            {
                "pending_action_id": pending_id,
                "user_id": "hitl-user",
                "thread_id": "hitl-thread",
            }
        )
    )
    wrong_owner = json.loads(
        cart_tools.confirm_save_preference.invoke(
            {
                "pending_action_id": pending_id,
                "user_id": "other-user",
                "thread_id": "hitl-thread",
                "expected_version": 1,
            }
        )
    )
    cancelled = json.loads(
        cart_tools.cancel_pending_action.invoke(
            {
                "pending_action_id": pending_id,
                "user_id": "hitl-user",
                "thread_id": "hitl-thread",
                "expected_version": 1,
            }
        )
    )

    assert missing_version["code"] == "expected_version_required"
    assert wrong_owner["code"] == "pending_action_not_found"
    assert cancelled["status"] == "cancelled"
    assert preference_session.query(UserPreference).count() == 0


def test_legacy_preference_action_fails_closed_on_confirm(preference_session: Session) -> None:
    legacy = PendingAction(
        id="legacy-preference-action",
        user_id="hitl-user",
        thread_id="hitl-thread",
        action_type="save_preference",
        payload_json={"preference_type": "avoid", "preference_value": "legacy"},
        risk_class="medium",
        preview_text="legacy preference",
        status="pending",
        version=1,
        expires_at=None,
        metadata_json={},
        result_json={},
    )
    preference_session.add(legacy)
    preference_session.commit()

    result = json.loads(
        cart_tools.confirm_save_preference.invoke(
            {
                "pending_action_id": legacy.id,
                "user_id": "hitl-user",
                "thread_id": "hitl-thread",
                "expected_version": 1,
            }
        )
    )

    assert result["status"] == "failed"
    assert result["code"] == "unsupported_action_schema"
    assert preference_session.query(UserPreference).count() == 0


def test_preference_write_rolls_back_when_repository_fails(
    preference_session: Session,
    monkeypatch,
) -> None:
    prepared = _prepare()

    def fail_write(*_args, **_kwargs):
        raise RuntimeError("preference storage failed")

    monkeypatch.setattr(preference_repository, "add_user_preference", fail_write)
    with pytest.raises(RuntimeError, match="preference storage failed"):
        cart_tools.confirm_save_preference.invoke(
            {
                "pending_action_id": prepared["pending_action_id"],
                "user_id": "hitl-user",
                "thread_id": "hitl-thread",
                "expected_version": 1,
            }
        )

    action = preference_session.get(PendingAction, prepared["pending_action_id"])
    assert action is not None
    assert action.status == "pending"
    assert preference_session.query(UserPreference).count() == 0
