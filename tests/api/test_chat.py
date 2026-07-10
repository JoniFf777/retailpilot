from types import SimpleNamespace

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
async def test_chat_uses_single_agent_by_default(monkeypatch) -> None:
    calls = []

    monkeypatch.setattr(
        agent_dependency,
        "get_settings",
        lambda: SimpleNamespace(shopmind_agent_mode="single"),
    )

    def fake_single_agent(
        message: str,
        user_id: str | None = None,
        thread_id: str | None = None,
    ) -> dict:
        calls.append(("single", message, user_id, thread_id))
        return {
            "answer": "single agent answer",
            "status": "completed",
            "tool_calls": ["search_products"],
        }

    def fake_multi_agent(
        message: str,
        user_id: str | None = None,
        thread_id: str | None = None,
    ) -> dict:
        calls.append(("multi", message, user_id, thread_id))
        return {"answer": "multi agent answer", "status": "completed", "tool_calls": []}

    monkeypatch.setattr(agent_dependency, "invoke_shopmind_agent", fake_single_agent)
    monkeypatch.setattr(agent_dependency, "invoke_shopmind_multi_agent", fake_multi_agent)

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
    assert calls == [("single", "推荐一个键盘", "user-001", "thread-001")]
    assert response.json() == {
        "answer": "single agent answer",
        "status": "completed",
        "tool_calls": ["search_products"],
        "user_id": "user-001",
        "thread_id": "thread-001",
        "pending_action_id": None,
    }


@pytest.mark.anyio
async def test_chat_multi_mode_keeps_response_schema(monkeypatch) -> None:
    calls = []

    monkeypatch.setattr(
        agent_dependency,
        "get_settings",
        lambda: SimpleNamespace(
            shopmind_agent_mode="multi",
            shopmind_supervisor_router="deterministic",
        ),
    )

    def fake_multi_agent(
        message: str,
        user_id: str | None = None,
        thread_id: str | None = None,
        supervisor_router=None,
    ) -> dict:
        assert supervisor_router is not None
        assert supervisor_router.route("推荐一个键盘")["router_type"] == "deterministic"
        calls.append((message, user_id, thread_id))
        return {
            "answer": "multi agent answer",
            "status": "completed",
            "tool_calls": ["search_products", "search_policy_docs"],
            "raw_result": {
                "routes": ["product_agent", "rag_agent"],
                "final_response": "internal detail",
            },
        }

    monkeypatch.setattr(agent_dependency, "invoke_shopmind_multi_agent", fake_multi_agent)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/chat",
            json={
                "message": "推荐键盘并说明退货政策",
                "user_id": "user-001",
                "thread_id": "thread-001",
            },
        )

    assert response.status_code == 200
    assert calls == [("推荐键盘并说明退货政策", "user-001", "thread-001")]
    assert response.json() == {
        "answer": "multi agent answer",
        "status": "completed",
        "tool_calls": ["search_products", "search_policy_docs"],
        "user_id": "user-001",
        "thread_id": "thread-001",
        "pending_action_id": None,
    }


@pytest.mark.anyio
async def test_chat_can_include_multi_agent_debug_metadata(monkeypatch) -> None:
    monkeypatch.setattr(
        agent_dependency,
        "get_settings",
        lambda: SimpleNamespace(
            shopmind_agent_mode="multi",
            shopmind_supervisor_router="deterministic",
        ),
    )

    def fake_multi_agent(
        message: str,
        user_id: str | None = None,
        thread_id: str | None = None,
        supervisor_router=None,
    ) -> dict:
        return {
            "answer": "multi agent answer",
            "status": "completed",
            "tool_calls": ["search_products"],
            "debug": {
                "supervisor_decision": {
                    "routes": ["product_agent"],
                    "router_type": "deterministic",
                },
                "agent_steps": [
                    {
                        "index": 1,
                        "node": "supervisor",
                        "router_type": "deterministic",
                    }
                ],
            },
            "raw_result": {
                "final_response": "internal detail",
                "product_summary": {"raw_detail": "SHOULD_NOT_LEAK"},
            },
        }

    monkeypatch.setattr(agent_dependency, "invoke_shopmind_multi_agent", fake_multi_agent)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/chat",
            json={
                "message": "推荐键盘",
                "user_id": "user-001",
                "thread_id": "thread-001",
                "include_debug": True,
            },
        )

    body = response.json()
    assert response.status_code == 200
    assert body["debug"]["supervisor_decision"]["routes"] == ["product_agent"]
    assert body["debug"]["agent_steps"][0]["node"] == "supervisor"
    assert "raw_result" not in body
    assert "SHOULD_NOT_LEAK" not in str(body)


@pytest.mark.anyio
async def test_chat_multi_mode_hands_write_intent_to_confirmation_path(monkeypatch) -> None:
    calls = []
    pending_action_id = "123e4567-e89b-12d3-a456-426614174000"

    monkeypatch.setattr(
        agent_dependency,
        "get_settings",
        lambda: SimpleNamespace(
            shopmind_agent_mode="multi",
            shopmind_supervisor_router="deterministic",
        ),
    )

    def fake_multi_agent(
        message: str,
        user_id: str | None = None,
        thread_id: str | None = None,
        supervisor_router=None,
    ) -> dict:
        calls.append(("multi", message, user_id, thread_id))
        return {
            "answer": "当前 V3 多 Agent 路径只支持只读查询。",
            "status": "completed",
            "tool_calls": [],
            "debug": {
                "supervisor_decision": {
                    "intent": "write_path_unsupported",
                    "routes": [],
                    "safety_flags": ["write_intent_blocked"],
                },
                "decision": {
                    "answer_type": "write_path_handoff",
                    "followup_reason": "read_only_multi_agent_write_intent",
                },
            },
            "raw_result": {
                "decision": {
                    "answer_type": "write_path_handoff",
                    "followup_reason": "read_only_multi_agent_write_intent",
                },
            },
        }

    def fake_single_agent(
        message: str,
        user_id: str | None = None,
        thread_id: str | None = None,
    ) -> dict:
        calls.append(("single", message, user_id, thread_id))
        return {
            "answer": "我已为你生成待确认加购，请确认是否加入购物车。",
            "status": "confirmation_required",
            "tool_calls": ["prepare_add_to_cart"],
            "pending_action_id": pending_action_id,
        }

    monkeypatch.setattr(agent_dependency, "invoke_shopmind_multi_agent", fake_multi_agent)
    monkeypatch.setattr(agent_dependency, "invoke_shopmind_agent", fake_single_agent)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/chat",
            json={
                "message": "帮我把 TECH-KEY-001 加入购物车",
                "user_id": "user-001",
                "thread_id": "thread-001",
                "include_debug": True,
            },
        )

    body = response.json()
    assert response.status_code == 200
    assert calls == [
        ("multi", "帮我把 TECH-KEY-001 加入购物车", "user-001", "thread-001"),
        ("single", "帮我把 TECH-KEY-001 加入购物车", "user-001", "thread-001"),
    ]
    assert body["answer"] == "我已为你生成待确认加购，请确认是否加入购物车。"
    assert body["status"] == "confirmation_required"
    assert body["tool_calls"] == ["prepare_add_to_cart"]
    assert body["pending_action_id"] == pending_action_id
    assert body["debug"]["multi_agent_handoff"] == {
        "from": "multi_agent_read_path",
        "to": "single_agent_write_path",
        "reason": "read_only_multi_agent_write_intent",
        "status": "confirmation_required",
    }
    assert body["debug"]["multi_agent_debug"]["supervisor_decision"]["routes"] == []
    assert "raw_result" not in body


@pytest.mark.anyio
async def test_chat_multi_mode_uses_real_v3_guardrail_for_write_handoff(
    monkeypatch,
) -> None:
    calls = []
    pending_action_id = "123e4567-e89b-12d3-a456-426614174111"

    monkeypatch.setattr(
        agent_dependency,
        "get_settings",
        lambda: SimpleNamespace(
            shopmind_agent_mode="multi",
            shopmind_supervisor_router="deterministic",
        ),
    )

    def fake_single_agent(
        message: str,
        user_id: str | None = None,
        thread_id: str | None = None,
    ) -> dict:
        calls.append(("single", message, user_id, thread_id))
        return {
            "answer": "我已为你生成待确认加购，请确认是否加入购物车。",
            "status": "confirmation_required",
            "tool_calls": ["prepare_add_to_cart"],
            "pending_action_id": pending_action_id,
        }

    monkeypatch.setattr(agent_dependency, "invoke_shopmind_agent", fake_single_agent)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/chat",
            json={
                "message": "帮我把 TECH-KEY-001 加入购物车",
                "user_id": "user-001",
                "thread_id": "thread-001",
                "include_debug": True,
            },
        )

    body = response.json()
    handoff_debug = body["debug"]["multi_agent_debug"]

    assert response.status_code == 200
    assert calls == [
        ("single", "帮我把 TECH-KEY-001 加入购物车", "user-001", "thread-001")
    ]
    assert body["status"] == "confirmation_required"
    assert body["tool_calls"] == ["prepare_add_to_cart"]
    assert body["pending_action_id"] == pending_action_id
    assert body["debug"]["multi_agent_handoff"]["reason"] == (
        "read_only_multi_agent_write_intent"
    )
    assert handoff_debug["supervisor_decision"]["intent"] == "write_path_unsupported"
    assert handoff_debug["supervisor_decision"]["routes"] == []
    assert handoff_debug["routes"] == []
    assert handoff_debug["executed_routes"] == []
    assert handoff_debug["decision"]["answer_type"] == "write_path_handoff"
    assert "write_intent_blocked" in handoff_debug["safety_flags"]
    assert "raw_result" not in body


@pytest.mark.anyio
async def test_chat_multi_mode_can_select_llm_supervisor_router(monkeypatch) -> None:
    calls = []

    monkeypatch.setattr(
        agent_dependency,
        "get_settings",
        lambda: SimpleNamespace(
            shopmind_agent_mode="multi",
            shopmind_supervisor_router="llm",
            workshop_model="openai:gpt-5-nano",
        ),
    )

    class FakeLLMRouter:
        def route(self, message: str, user_id: str | None = None) -> dict:
            return {"router_type": "llm"}

    def fake_create_supervisor_router(router_mode: str, model=None):
        calls.append(("router_factory", router_mode, model))
        return FakeLLMRouter()

    monkeypatch.setattr(
        agent_dependency,
        "create_supervisor_router",
        fake_create_supervisor_router,
    )

    def fake_multi_agent(
        message: str,
        user_id: str | None = None,
        thread_id: str | None = None,
        supervisor_router=None,
    ) -> dict:
        decision = supervisor_router.route(message, user_id=user_id)
        calls.append((message, user_id, thread_id, decision["router_type"]))
        return {
            "answer": "multi agent answer",
            "status": "completed",
            "tool_calls": [],
        }

    monkeypatch.setattr(agent_dependency, "invoke_shopmind_multi_agent", fake_multi_agent)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/chat",
            json={
                "message": "推荐键盘",
                "user_id": "user-001",
                "thread_id": "thread-001",
            },
        )

    assert response.status_code == 200
    assert calls == [
        ("router_factory", "llm", "openai:gpt-5-nano"),
        ("推荐键盘", "user-001", "thread-001", "llm"),
    ]
    assert response.json()["answer"] == "multi agent answer"


@pytest.mark.anyio
async def test_chat_rejects_empty_message() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/chat", json={"message": ""})

    assert response.status_code == 422
