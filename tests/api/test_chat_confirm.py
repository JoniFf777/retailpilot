import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies import agent as agent_dependency
from app.main import app


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_chat_confirm_confirmed_true_returns_completed(monkeypatch) -> None:
    def fake_confirm_pending_action(
        pending_action_id: str,
        user_id: str,
        confirmed: bool,
    ) -> dict:
        assert pending_action_id == "pending-001"
        assert user_id == "user-001"
        assert confirmed is True
        return {
            "answer": "已确认加入购物车。",
            "status": "completed",
            "tool_calls": ["confirm_add_to_cart"],
            "pending_action_id": pending_action_id,
        }

    monkeypatch.setattr(agent_dependency, "confirm_pending_action", fake_confirm_pending_action)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/chat/confirm",
            json={
                "user_id": "user-001",
                "pending_action_id": "pending-001",
                "confirmed": True,
                "thread_id": "thread-001",
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "answer": "已确认加入购物车。",
        "status": "completed",
        "tool_calls": ["confirm_add_to_cart"],
        "user_id": "user-001",
        "thread_id": "thread-001",
        "pending_action_id": "pending-001",
    }


@pytest.mark.anyio
async def test_chat_confirm_confirmed_false_returns_cancelled(monkeypatch) -> None:
    def fake_confirm_pending_action(
        pending_action_id: str,
        user_id: str,
        confirmed: bool,
    ) -> dict:
        assert pending_action_id == "pending-002"
        assert user_id == "user-001"
        assert confirmed is False
        return {
            "answer": "已取消待确认动作。",
            "status": "cancelled",
            "tool_calls": ["cancel_pending_action"],
            "pending_action_id": pending_action_id,
        }

    monkeypatch.setattr(agent_dependency, "confirm_pending_action", fake_confirm_pending_action)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/chat/confirm",
            json={
                "user_id": "user-001",
                "pending_action_id": "pending-002",
                "confirmed": False,
            },
        )

    assert response.status_code == 200
    assert response.json()["answer"] == "已取消待确认动作。"
    assert response.json()["status"] == "cancelled"
    assert response.json()["tool_calls"] == ["cancel_pending_action"]
    assert response.json()["pending_action_id"] == "pending-002"


@pytest.mark.anyio
async def test_chat_confirm_returns_chinese_error_answer(monkeypatch) -> None:
    def fake_confirm_pending_action(
        pending_action_id: str,
        user_id: str,
        confirmed: bool,
    ) -> dict:
        return {
            "answer": "无法确认加入购物车：用户不匹配。",
            "status": "failed",
            "tool_calls": ["confirm_add_to_cart"],
            "pending_action_id": pending_action_id,
        }

    monkeypatch.setattr(agent_dependency, "confirm_pending_action", fake_confirm_pending_action)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/chat/confirm",
            json={
                "user_id": "wrong-user",
                "pending_action_id": "pending-003",
                "confirmed": True,
            },
        )

    assert response.status_code == 200
    assert response.json()["answer"] == "无法确认加入购物车：用户不匹配。"
    assert response.json()["status"] == "failed"


def test_confirm_pending_action_adds_confirmation_debug(monkeypatch) -> None:
    class FakeConfirmTool:
        @staticmethod
        def invoke(payload: dict) -> str:
            return "已确认加入购物车。"

    monkeypatch.setattr(agent_dependency, "confirm_add_to_cart", FakeConfirmTool())

    result = agent_dependency.confirm_pending_action(
        pending_action_id="pending-debug-confirm",
        user_id="user-001",
        confirmed=True,
    )
    event = result["debug"]["confirmation"]["events"][0]

    assert result["status"] == "completed"
    assert event == {
        "index": 1,
        "event": "pending_action_confirmed",
        "requested_confirmation": True,
        "status": "completed",
        "tool_call": "confirm_add_to_cart",
    }


def test_confirm_pending_action_adds_cancellation_debug(monkeypatch) -> None:
    class FakeCancelTool:
        @staticmethod
        def invoke(payload: dict) -> str:
            return "已取消待确认动作。"

    monkeypatch.setattr(agent_dependency, "cancel_pending_action", FakeCancelTool())

    result = agent_dependency.confirm_pending_action(
        pending_action_id="pending-debug-cancel",
        user_id="user-001",
        confirmed=False,
    )
    event = result["debug"]["confirmation"]["events"][0]

    assert result["status"] == "cancelled"
    assert event == {
        "index": 1,
        "event": "pending_action_cancelled",
        "requested_confirmation": False,
        "status": "cancelled",
        "tool_call": "cancel_pending_action",
    }


@pytest.mark.anyio
async def test_chat_confirm_can_include_confirmation_debug(monkeypatch) -> None:
    def fake_confirm_pending_action(
        pending_action_id: str,
        user_id: str,
        confirmed: bool,
    ) -> dict:
        return {
            "answer": "已确认加入购物车。",
            "status": "completed",
            "tool_calls": ["confirm_add_to_cart"],
            "pending_action_id": pending_action_id,
            "debug": {
                "confirmation": {
                    "events": [
                        {
                            "index": 1,
                            "event": "pending_action_confirmed",
                            "requested_confirmation": True,
                            "status": "completed",
                            "tool_call": "confirm_add_to_cart",
                        }
                    ]
                }
            },
        }

    monkeypatch.setattr(agent_dependency, "confirm_pending_action", fake_confirm_pending_action)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/chat/confirm",
            json={
                "user_id": "user-001",
                "pending_action_id": "pending-004",
                "confirmed": True,
                "include_debug": True,
            },
        )

    body = response.json()
    assert response.status_code == 200
    assert body["debug"]["confirmation"]["events"][0]["event"] == (
        "pending_action_confirmed"
    )
