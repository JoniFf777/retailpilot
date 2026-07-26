from __future__ import annotations

import json

import httpx
import pytest

from app.runtime import AgentEvent, EventVisibility
from app.runtime.streaming import encode_sse_event
from examples import shopmind_reference_client as reference


def _owner_counts() -> dict[str, int]:
    return {
        "preferences": 0,
        "cart_items": 0,
        "pending_actions": 0,
        "candidate_contexts": 0,
        "conversation_threads": 1,
        "conversation_messages": 2,
        "agent_runs": 1,
        "agent_run_events": 2,
        "conversation_summaries": 0,
        "idempotency_records": 0,
        "memory_records": 0,
    }


def _run_payload() -> dict:
    return {
        "schema_version": "shopmind.owner-run-inspection.v1",
        "run_id": "run-1",
        "trace_id": "trace-1",
        "thread_id": "thread-1",
        "operation": "chat",
        "mode": "multi",
        "status": "completed",
        "pending_action_id": None,
        "usage": {
            "input_tokens": None,
            "output_tokens": None,
            "total_tokens": None,
            "cost_usd": None,
            "tool_call_count": 1,
            "step_count": 2,
        },
        "started_at": "2026-07-27T00:00:00Z",
        "completed_at": "2026-07-27T00:00:01Z",
        "client_event_count": 2,
        "events": [
            {
                "sequence": 1,
                "event_type": "run.started",
                "agent_name": None,
                "visibility": "client",
                "created_at": "2026-07-27T00:00:00Z",
            },
            {
                "sequence": 2,
                "event_type": "run.completed",
                "agent_name": None,
                "visibility": "client",
                "created_at": "2026-07-27T00:00:01Z",
            },
        ],
        "event_limit": 50,
        "events_truncated": False,
    }


def test_reference_client_uses_only_public_json_boundaries() -> None:
    requests: list[tuple[str, dict, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append(
            (
                request.url.path,
                payload,
                request.headers.get("Idempotency-Key"),
            )
        )
        if request.url.path == "/api/chat":
            return httpx.Response(
                200,
                json={
                    "answer": "ok",
                    "status": "completed",
                    "tool_calls": [],
                    "user_id": "owner-1",
                    "thread_id": "thread-1",
                    "pending_action_id": None,
                    "run_id": "run-1",
                    "trace_id": "trace-1",
                    "debug": {"routes": []},
                },
            )
        if request.url.path == "/api/chat/confirm":
            return httpx.Response(
                200,
                json={
                    "answer": "confirmed",
                    "status": "completed",
                    "tool_calls": ["confirm_add_to_cart"],
                    "user_id": "owner-1",
                    "thread_id": "thread-1",
                    "pending_action_id": "action-1",
                    "run_id": "run-2",
                    "trace_id": "trace-2",
                },
            )
        if request.url.path == "/api/owner-data/inspect":
            return httpx.Response(
                200,
                json={
                    "counts": _owner_counts(),
                    "total_records": 5,
                    "memories": [],
                    "memory_limit": 10,
                    "memory_truncated": False,
                },
            )
        if request.url.path == "/api/owner-data/runs/inspect":
            return httpx.Response(200, json=_run_payload())
        raise AssertionError(request.url.path)

    with reference.ShopMindReferenceClient(
        transport=httpx.MockTransport(handler)
    ) as client:
        chat = client.chat(
            message="recommend",
            user_id="owner-1",
            thread_id="thread-1",
            idempotency_key="chat-key",
        )
        confirmed = client.confirm(
            user_id="owner-1",
            pending_action_id="action-1",
            confirmed=True,
            thread_id="thread-1",
            updated_arguments={"quantity": 2},
            idempotency_key="confirm-key",
        )
        memory = client.inspect_memory(user_id="owner-1", memory_limit=10)
        run = client.inspect_run(
            user_id="owner-1",
            trace_id="trace-1",
        )

    assert (chat.run_id, chat.trace_id) == ("run-1", "trace-1")
    assert confirmed.status == "completed"
    assert memory.counts.agent_runs == 1
    assert run.run_id == "run-1"
    assert [request[0] for request in requests] == [
        "/api/chat",
        "/api/chat/confirm",
        "/api/owner-data/inspect",
        "/api/owner-data/runs/inspect",
    ]
    assert requests[0][2] == "chat-key"
    assert requests[1][1]["updated_arguments"] == {"quantity": 2}
    assert requests[1][2] == "confirm-key"
    assert requests[3][1] == {
        "user_id": "owner-1",
        "trace_id": "trace-1",
        "event_limit": 50,
    }


def test_reference_client_parses_ordered_sse_and_final_runtime_identity() -> None:
    events = [
        AgentEvent(
            sequence=1,
            event_type="run.started",
            visibility=EventVisibility.CLIENT,
            trace_id="trace-1",
            payload={"operation": "chat"},
        ),
        AgentEvent(
            sequence=2,
            event_type="run.result",
            visibility=EventVisibility.CLIENT,
            trace_id="trace-1",
            payload={
                "answer": "done",
                "status": "completed",
                "tool_calls": [],
                "user_id": "owner-1",
                "thread_id": "thread-1",
                "pending_action_id": None,
                "run_id": "run-1",
                "trace_id": "trace-1",
            },
        ),
    ]
    content = "".join(encode_sse_event(event) for event in events)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/chat/stream"
        assert request.headers["accept"] == "text/event-stream"
        return httpx.Response(
            200,
            text=content,
            headers={"content-type": "text/event-stream"},
        )

    with reference.ShopMindReferenceClient(
        transport=httpx.MockTransport(handler)
    ) as client:
        received = list(
            client.stream_chat(
                message="stream",
                user_id="owner-1",
                thread_id="thread-1",
            )
        )

    assert [event.event_type for event in received] == [
        "run.started",
        "run.result",
    ]
    assert received[-1].payload["run_id"] == "run-1"
    assert received[-1].trace_id == "trace-1"


@pytest.mark.parametrize(
    "value",
    (
        "http://example.com/api",
        "https://user:secret@example.com/api",
        "https://example.com/api?token=private",
        "file:///tmp/api",
    ),
)
def test_reference_client_rejects_unsafe_base_urls(value: str) -> None:
    with pytest.raises(ValueError, match="base URL|require HTTPS") as raised:
        reference.validate_base_url(value)
    assert value not in str(raised.value)


def test_reference_client_bounds_and_sanitizes_failures() -> None:
    private_body = "private response body with credential"

    def failed(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            503,
            text=private_body,
            headers={"content-type": "text/plain"},
        )

    with reference.ShopMindReferenceClient(
        transport=httpx.MockTransport(failed)
    ) as client:
        with pytest.raises(reference.ReferenceClientError) as raised:
            client.chat(
                message="test",
                user_id="owner-1",
                thread_id="thread-1",
            )
    assert raised.value.code == "request_failed_503"
    assert private_body not in str(raised.value)

    def oversized(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"{}" * 20,
            headers={"content-type": "application/json"},
        )

    with reference.ShopMindReferenceClient(
        transport=httpx.MockTransport(oversized),
        max_response_bytes=10,
    ) as client:
        with pytest.raises(
            reference.ReferenceClientError,
            match="response_too_large",
        ):
            client.chat(
                message="test",
                user_id="owner-1",
                thread_id="thread-1",
            )


def test_reference_client_rejects_out_of_order_stream() -> None:
    content = "".join(
        encode_sse_event(
            AgentEvent(
                sequence=sequence,
                event_type="run.started",
                visibility=EventVisibility.CLIENT,
            )
        )
        for sequence in (2, 1)
    )

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text=content,
            headers={"content-type": "text/event-stream"},
        )

    with reference.ShopMindReferenceClient(
        transport=httpx.MockTransport(handler)
    ) as client:
        with pytest.raises(
            reference.ReferenceClientError,
            match="stream_bounds_exceeded",
        ):
            list(
                client.stream_chat(
                    message="test",
                    user_id="owner-1",
                    thread_id="thread-1",
                )
            )


def test_reference_client_rejects_oversized_stream_event_before_termination(
    monkeypatch,
) -> None:
    monkeypatch.setattr(reference, "MAX_SSE_EVENT_BYTES", 32)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text=f"data: {'x' * 40}",
            headers={"content-type": "text/event-stream"},
        )

    with reference.ShopMindReferenceClient(
        transport=httpx.MockTransport(handler)
    ) as client:
        with pytest.raises(
            reference.ReferenceClientError,
            match="stream_event_too_large",
        ):
            list(
                client.stream_chat(
                    message="test",
                    user_id="owner-1",
                    thread_id="thread-1",
                )
            )


def test_reference_client_cli_prints_closed_json(monkeypatch, capsys) -> None:
    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def chat(self, **_kwargs):
            from app.schemas.chat import ChatResponse

            return ChatResponse(
                answer="ok",
                status="completed",
                user_id="owner-1",
                thread_id="thread-1",
                run_id="run-1",
                trace_id="trace-1",
            )

    monkeypatch.setattr(reference, "ShopMindReferenceClient", FakeClient)

    assert (
        reference.main(
            [
                "chat",
                "--message",
                "test",
                "--user-id",
                "owner-1",
                "--thread-id",
                "thread-1",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["run_id"] == "run-1"
    assert payload["trace_id"] == "trace-1"
