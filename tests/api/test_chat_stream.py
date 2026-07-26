import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies import agent as agent_dependency
from app.api.routes import chat_stream
from app.main import app
from app.runtime import AgentEvent, EventVisibility
from app.runtime.streaming import STREAM_ADMISSION_CONTROLLER


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_chat_stream_emits_runtime_events_and_final_result(monkeypatch) -> None:
    def fake_call_shopmind_agent(
        message: str,
        user_id: str | None = None,
        thread_id: str | None = None,
        *,
        event_sink=None,
        cancellation_check=None,
    ) -> dict:
        assert message == "recommend a keyboard"
        assert user_id == "stream-user"
        assert thread_id == "stream-thread"
        assert cancellation_check is not None
        event_sink(
            AgentEvent(
                sequence=1,
                event_type="run.started",
                visibility=EventVisibility.CLIENT,
                payload={"operation": "chat"},
            )
        )
        event_sink(
            AgentEvent(
                sequence=2,
                event_type="agent.completed",
                visibility=EventVisibility.CLIENT,
                payload={"agent_name": "product_agent"},
            )
        )
        return {
            "answer": "Try MX Keys.",
            "status": "completed",
            "tool_calls": ["search_products"],
            "pending_action_id": None,
        }

    monkeypatch.setattr(agent_dependency, "call_shopmind_agent", fake_call_shopmind_agent)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        responses = [
            await client.post(
                "/api/chat/stream",
                json={
                    "message": "recommend a keyboard",
                    "user_id": "stream-user",
                    "thread_id": "stream-thread",
                },
            )
            for _ in range(5)
        ]

    for response in responses:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert "event: run.started" in response.text
        assert "event: agent.completed" in response.text
        assert "event: run.result" in response.text
        assert response.text.index("event: run.started") < response.text.index(
            "event: agent.completed"
        ) < response.text.index("event: run.result")
        assert "Try MX Keys." in response.text
        assert "search_products" in response.text


@pytest.mark.anyio
async def test_chat_stream_debug_result_includes_runtime_identity(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        agent_dependency,
        "call_shopmind_agent",
        lambda *_args, **_kwargs: {
            "answer": "ok",
            "status": "completed",
            "tool_calls": [],
            "run_id": "stream-run-1",
            "trace_id": "stream-trace-1",
        },
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/chat/stream",
            json={"message": "test", "include_debug": True},
        )

    assert response.status_code == 200
    assert '"run_id": "stream-run-1"' in response.text
    assert '"trace_id": "stream-trace-1"' in response.text


@pytest.mark.anyio
async def test_chat_stream_rejects_when_local_concurrency_limit_is_reached(monkeypatch) -> None:
    monkeypatch.setattr(
        chat_stream,
        "get_settings",
        lambda: type(
            "Settings",
            (),
            {
                "shopmind_stream_max_concurrency": 1,
                "shopmind_stream_event_buffer_size": 8,
                "shopmind_stream_admission_lease_ttl_ms": 30_000,
                "shopmind_stream_admission_renew_interval_ms": 10_000,
            },
        )(),
    )
    admission = STREAM_ADMISSION_CONTROLLER.try_acquire(
        1,
        lease_ttl_ms=30_000,
    )
    assert admission.accepted is True

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/chat/stream",
                json={"message": "recommend a keyboard"},
            )
    finally:
        STREAM_ADMISSION_CONTROLLER.release(admission.lease_id)

    assert response.status_code == 429
    assert response.json()["detail"] == "Too many active streaming runs."


@pytest.mark.anyio
async def test_chat_stream_forwards_optional_idempotency_header(monkeypatch) -> None:
    def fake_call_shopmind_agent(
        message: str,
        user_id: str | None = None,
        thread_id: str | None = None,
        *,
        idempotency_key: str | None = None,
        event_sink=None,
        cancellation_check=None,
    ) -> dict:
        assert idempotency_key == "stream-idem-1"
        return {"answer": "ok", "status": "completed", "tool_calls": []}

    monkeypatch.setattr(agent_dependency, "call_shopmind_agent", fake_call_shopmind_agent)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/chat/stream",
            headers={"Idempotency-Key": "stream-idem-1"},
            json={"message": "recommend a keyboard"},
        )

    assert response.status_code == 200
    assert "event: run.result" in response.text
