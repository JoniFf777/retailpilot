import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies import agent as agent_dependency
from app.main import app


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_chat_returns_agent_answer(monkeypatch) -> None:
    def fake_call_shopmind_agent(
        message: str,
        user_id: str | None = None,
        thread_id: str | None = None,
    ) -> dict:
        assert message == "推荐一个键盘"
        assert user_id == "user-001"
        assert thread_id == "thread-001"
        return {
            "answer": "可以考虑 Logitech MX Keys，它适合办公使用。",
            "tool_calls": ["search_products"],
        }

    monkeypatch.setattr(agent_dependency, "call_shopmind_agent", fake_call_shopmind_agent)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/chat",
            json={
                "message": "推荐一个键盘",
                "user_id": "user-001",
                "thread_id": "thread-001",
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "answer": "可以考虑 Logitech MX Keys，它适合办公使用。",
        "status": "completed",
        "tool_calls": ["search_products"],
        "user_id": "user-001",
        "thread_id": "thread-001",
        "pending_action_id": None,
    }


@pytest.mark.anyio
async def test_chat_accepts_chinese_message(monkeypatch) -> None:
    captured = {}

    def fake_call_shopmind_agent(
        message: str,
        user_id: str | None = None,
        thread_id: str | None = None,
    ) -> dict:
        captured["message"] = message
        captured["user_id"] = user_id
        captured["thread_id"] = thread_id
        return {
            "answer": "已收到你的中文问题。",
            "status": "completed",
            "tool_calls": [],
        }

    monkeypatch.setattr(agent_dependency, "call_shopmind_agent", fake_call_shopmind_agent)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/chat", json={"message": "我想买一台适合办公的显示器"})

    assert response.status_code == 200
    assert captured["message"] == "我想买一台适合办公的显示器"
    assert captured["user_id"] is None
    assert captured["thread_id"] is None
    assert response.json()["answer"] == "已收到你的中文问题。"
    assert response.json()["status"] == "completed"
    assert response.json()["tool_calls"] == []
    assert response.json()["pending_action_id"] is None


@pytest.mark.anyio
async def test_chat_returns_pending_action_when_confirmation_required(monkeypatch) -> None:
    pending_action_id = "123e4567-e89b-12d3-a456-426614174000"

    def fake_call_shopmind_agent(
        message: str,
        user_id: str | None = None,
        thread_id: str | None = None,
    ) -> dict:
        assert message == "帮我把这个键盘加入购物车"
        assert user_id == "user-001"
        assert thread_id == "thread-001"
        return {
            "answer": "我已为你生成待确认加购，请确认是否加入购物车。",
            "status": "confirmation_required",
            "tool_calls": ["prepare_add_to_cart"],
            "pending_action_id": pending_action_id,
        }

    monkeypatch.setattr(agent_dependency, "call_shopmind_agent", fake_call_shopmind_agent)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/chat",
            json={
                "message": "帮我把这个键盘加入购物车",
                "user_id": "user-001",
                "thread_id": "thread-001",
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "answer": "我已为你生成待确认加购，请确认是否加入购物车。",
        "status": "confirmation_required",
        "tool_calls": ["prepare_add_to_cart"],
        "user_id": "user-001",
        "thread_id": "thread-001",
        "pending_action_id": pending_action_id,
    }


@pytest.mark.anyio
async def test_chat_rejects_empty_message() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/chat", json={"message": ""})

    assert response.status_code == 422
