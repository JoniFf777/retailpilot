import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies import agent as agent_dependency
from app.main import app
from app.runtime import ToolCallRecord, ToolSideEffectClass


def resolve_add_to_cart(**_kwargs) -> dict:
    return {"status": "resolved", "action_type": "add_to_cart"}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_chat_confirm_confirmed_true_returns_completed(monkeypatch) -> None:
    def fake_confirm_pending_action(
        pending_action_id: str,
        user_id: str,
        confirmed: bool,
        thread_id: str | None = None,
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
        thread_id: str | None = None,
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
async def test_chat_confirm_forwards_optional_idempotency_header(monkeypatch) -> None:
    def fake_confirm_pending_action(
        pending_action_id: str,
        user_id: str,
        confirmed: bool,
        thread_id: str | None = None,
        *,
        idempotency_key: str | None = None,
    ) -> dict:
        assert pending_action_id == "pending-idem-1"
        assert idempotency_key == "confirm-idem-1"
        return {
            "answer": "ok",
            "status": "completed",
            "tool_calls": ["confirm_add_to_cart"],
            "pending_action_id": pending_action_id,
        }

    monkeypatch.setattr(agent_dependency, "confirm_pending_action", fake_confirm_pending_action)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/chat/confirm",
            headers={"Idempotency-Key": "confirm-idem-1"},
            json={
                "user_id": "user-001",
                "pending_action_id": "pending-idem-1",
                "confirmed": True,
            },
        )

    assert response.status_code == 200
    assert response.json()["pending_action_id"] == "pending-idem-1"


@pytest.mark.anyio
async def test_chat_confirm_forwards_optional_server_validated_edits(monkeypatch) -> None:
    def fake_confirm_pending_action(
        pending_action_id: str,
        user_id: str,
        confirmed: bool,
        thread_id: str | None = None,
        *,
        updated_arguments: dict | None = None,
    ) -> dict:
        assert confirmed is True
        assert updated_arguments == {"quantity": 2}
        return {
            "answer": "ok",
            "status": "completed",
            "tool_calls": ["confirm_add_to_cart"],
            "pending_action_id": pending_action_id,
        }

    monkeypatch.setattr(
        agent_dependency, "confirm_pending_action", fake_confirm_pending_action
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/chat/confirm",
            json={
                "user_id": "user-001",
                "pending_action_id": "pending-edit-1",
                "confirmed": True,
                "updated_arguments": {"quantity": 2},
            },
        )

    assert response.status_code == 200
    assert response.json()["status"] == "completed"


@pytest.mark.anyio
async def test_chat_confirm_returns_chinese_error_answer(monkeypatch) -> None:
    def fake_confirm_pending_action(
        pending_action_id: str,
        user_id: str,
        confirmed: bool,
        thread_id: str | None = None,
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
    monkeypatch.setattr(agent_dependency, "resolve_pending_action", resolve_add_to_cart)

    class FakeConfirmTool:
        name = "confirm_add_to_cart"

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
    monkeypatch.setattr(agent_dependency, "resolve_pending_action", resolve_add_to_cart)

    class FakeCancelTool:
        name = "cancel_pending_action"

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


def test_confirm_boundary_routes_sensitive_call_through_gateway(monkeypatch) -> None:
    monkeypatch.setattr(agent_dependency, "resolve_pending_action", resolve_add_to_cart)

    class FakeGateway:
        def invoke(self, *, agent_name, tool, arguments, context):
            assert agent_name == "confirmation_boundary"
            assert tool.name == "confirm_add_to_cart"
            assert arguments["user_id"] == "user-001"
            assert context.policy.allow_sensitive_tools is True
            return "已确认加入购物车。", ToolCallRecord(
                tool_name=tool.name,
                caller=agent_name,
                capability=tool.name,
                side_effect_class=ToolSideEffectClass.SENSITIVE_WRITE,
            )

    class FakeConfirmTool:
        name = "confirm_add_to_cart"

    monkeypatch.setattr(agent_dependency, "tool_gateway", FakeGateway())
    monkeypatch.setattr(agent_dependency, "confirm_add_to_cart", FakeConfirmTool())
    monkeypatch.setattr(agent_dependency, "resolve_pending_action", resolve_add_to_cart)

    result = agent_dependency.confirm_pending_action(
        pending_action_id="pending-gateway-confirm",
        user_id="user-001",
        confirmed=True,
    )

    assert result["status"] == "completed"


def test_confirm_boundary_dispatches_registered_preference_handler(monkeypatch) -> None:
    class FakeGateway:
        def invoke(self, *, agent_name, tool, arguments, context):
            assert agent_name == "confirmation_boundary"
            assert tool.name == "confirm_save_preference"
            assert arguments["pending_action_id"] == "pending-preference"
            return "已确认保存购物偏好。", ToolCallRecord(
                tool_name=tool.name,
                caller=agent_name,
                capability=tool.name,
                side_effect_class=ToolSideEffectClass.SENSITIVE_WRITE,
            )

    class FakePreferenceTool:
        name = "confirm_save_preference"

    monkeypatch.setattr(agent_dependency, "tool_gateway", FakeGateway())
    monkeypatch.setattr(
        agent_dependency, "confirm_save_preference", FakePreferenceTool()
    )
    monkeypatch.setattr(
        agent_dependency,
        "resolve_pending_action",
        lambda **_kwargs: {
            "status": "resolved",
            "action_type": "save_preference",
        },
    )

    events = []
    result = agent_dependency.confirm_pending_action(
        pending_action_id="pending-preference",
        user_id="user-001",
        thread_id="thread-001",
        confirmed=True,
        event_sink=events.append,
    )

    assert result["status"] == "completed"
    assert result["tool_calls"] == ["confirm_save_preference"]
    assert result["debug"]["confirmation"]["events"][0]["action_type"] == (
        "save_preference"
    )
    action_event = next(event for event in events if event.event_type == "action.confirmed")
    assert action_event.payload == {
        "action_id": "pending-preference",
        "action_type": "save_preference",
        "status": "confirmed",
        "tool_call": "confirm_save_preference",
    }
    assert [event.sequence for event in events] == list(range(1, len(events) + 1))


def test_confirm_boundary_orders_resumed_edited_and_confirmed_events(monkeypatch) -> None:
    class FakeGateway:
        def invoke(self, *, agent_name, tool, arguments, context):
            assert arguments["updated_arguments"] == {
                "preference_value": "silent switches"
            }
            return "saved", ToolCallRecord(
                tool_name=tool.name,
                caller=agent_name,
                capability=tool.name,
                side_effect_class=ToolSideEffectClass.SENSITIVE_WRITE,
            )

    class FakePreferenceTool:
        name = "confirm_save_preference"

    monkeypatch.setattr(agent_dependency, "tool_gateway", FakeGateway())
    monkeypatch.setattr(
        agent_dependency, "confirm_save_preference", FakePreferenceTool()
    )
    monkeypatch.setattr(
        agent_dependency,
        "resolve_pending_action",
        lambda **_kwargs: {
            "status": "resolved",
            "action_status": "pending",
            "action_type": "save_preference",
        },
    )
    events = []

    result = agent_dependency.confirm_pending_action(
        pending_action_id="pending-edit",
        user_id="user-001",
        confirmed=True,
        updated_arguments={"preference_value": " silent switches "},
        event_sink=events.append,
    )

    lifecycle = [
        event for event in events if event.event_type.startswith("action.")
    ]
    assert result["status"] == "completed"
    assert [event.event_type for event in lifecycle] == [
        "action.resumed",
        "action.edited",
        "action.confirmed",
    ]
    assert lifecycle[1].payload["updated_fields"] == ["preference_value"]
    assert "silent switches" not in str(lifecycle[1].payload)


def test_confirm_boundary_rejects_forbidden_edit_before_gateway(monkeypatch) -> None:
    class FailingGateway:
        def invoke(self, **_kwargs):
            raise AssertionError("gateway must not run")

    monkeypatch.setattr(agent_dependency, "tool_gateway", FailingGateway())
    monkeypatch.setattr(
        agent_dependency,
        "resolve_pending_action",
        lambda **_kwargs: {
            "status": "resolved",
            "action_status": "pending",
            "action_type": "add_to_cart",
        },
    )
    events = []

    result = agent_dependency.confirm_pending_action(
        pending_action_id="pending-edit",
        user_id="user-001",
        confirmed=True,
        updated_arguments={"product_id": "OTHER"},
        event_sink=events.append,
    )

    assert result["status"] == "failed"
    assert result["tool_calls"] == []
    assert [
        event.event_type
        for event in events
        if event.event_type.startswith("action.")
    ] == ["action.resumed", "action.failed"]
    assert events[-2].payload["reason"] == "invalid_edit"


def test_confirm_boundary_rejects_unresolved_action_before_tool(monkeypatch) -> None:
    class FailingGateway:
        def invoke(self, **_kwargs):
            raise AssertionError("gateway must not run")

    monkeypatch.setattr(agent_dependency, "tool_gateway", FailingGateway())
    monkeypatch.setattr(
        agent_dependency,
        "resolve_pending_action",
        lambda **_kwargs: {"status": "error", "message": "user mismatch"},
    )

    result = agent_dependency.confirm_pending_action(
        pending_action_id="other-user-action",
        user_id="user-001",
        confirmed=True,
    )

    assert result["status"] == "failed"
    assert result["tool_calls"] == []


def test_confirm_boundary_emits_failed_event_when_handler_raises(monkeypatch) -> None:
    class FailingGateway:
        def invoke(self, **_kwargs):
            raise RuntimeError("private handler detail")

    monkeypatch.setattr(agent_dependency, "tool_gateway", FailingGateway())
    monkeypatch.setattr(
        agent_dependency,
        "resolve_pending_action",
        lambda **_kwargs: {
            "status": "resolved",
            "action_type": "save_preference",
        },
    )
    events = []

    with pytest.raises(RuntimeError, match="private handler detail"):
        agent_dependency.confirm_pending_action(
            pending_action_id="failed-preference",
            user_id="user-001",
            confirmed=True,
            event_sink=events.append,
        )

    failure = next(event for event in events if event.event_type == "action.failed")
    assert failure.payload["reason"] == "handler_failed"
    assert "private" not in str(failure.payload)


@pytest.mark.anyio
async def test_chat_confirm_can_include_confirmation_debug(monkeypatch) -> None:
    def fake_confirm_pending_action(
        pending_action_id: str,
        user_id: str,
        confirmed: bool,
        thread_id: str | None = None,
    ) -> dict:
        return {
            "answer": "已确认加入购物车。",
            "status": "completed",
            "tool_calls": ["confirm_add_to_cart"],
            "pending_action_id": pending_action_id,
            "run_id": "confirm-run-004",
            "trace_id": "confirm-trace-004",
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
    assert body["run_id"] == "confirm-run-004"
    assert body["trace_id"] == "confirm-trace-004"
