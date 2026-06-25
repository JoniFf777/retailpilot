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
