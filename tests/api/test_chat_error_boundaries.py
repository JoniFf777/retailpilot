from __future__ import annotations

import logging

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.chat_response import build_chat_response
from app.core.chat_errors import log_public_exception, public_error
from app.dependencies import agent as agent_dependency
from app.main import app
from app.runtime import ErrorSource, RunError, RunResult, RunStatus


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _failed_run(
    *,
    code: str = "runtime.executor_exception",
    answer: str = "private SQL table=users / traceback",
    debug: dict | None = None,
    retry_state: str = "terminal",
) -> RunResult:
    return RunResult(
        run_id="run-error-1",
        runtime_thread_id="runtime-thread-1",
        trace_id="trace-error-1",
        request_id="request-error-1",
        status=RunStatus.FAILED,
        answer=answer,
        error=RunError(
            code=code,
            message="safe runtime message",
            source=ErrorSource.AGENT,
        ),
        debug=debug,
        metadata={
            "retry_state": retry_state,
            "authoritative_run_id": "winner-run-1"
            if retry_state == "in_progress"
            else None,
        },
    )


def test_failed_run_error_wins_over_raw_answer_and_debug_is_bounded() -> None:
    response = build_chat_response(
        _failed_run(
            debug={
                "agent_steps": [{"node": "product_agent"}],
                "exception_text": "private traceback SQL driver detail",
                "provider_payload": {"secret": "do-not-leak"},
                "safe_reason": "bounded reason",
            }
        ),
        user_id="user-1",
        thread_id="thread-1",
        include_debug=True,
    )

    body = response.model_dump(mode="json")
    assert body["status"] == "failed"
    assert body["runtime_error_code"] == "runtime.executor_exception"
    assert body["answer"] != "private SQL table=users / traceback"
    assert "private SQL" not in str(body)
    assert body["debug"] == {
        "agent_steps": [{"node": "product_agent"}],
        "safe_reason": "bounded reason",
    }


def test_in_progress_projection_remains_nonterminal() -> None:
    response = build_chat_response(
        _failed_run(
            code="runtime.idempotency_in_progress",
            retry_state="in_progress",
        ),
        user_id="user-1",
        thread_id="thread-1",
        include_debug=False,
    )

    assert response.retry_state == "in_progress"
    assert response.runtime_error_code == "runtime.idempotency_in_progress"
    assert response.authoritative_run_id == "winner-run-1"
    assert response.status == "failed"
    assert "仍在处理中" in response.answer


def test_unknown_error_code_maps_to_bounded_generic_error() -> None:
    projection = public_error("private.provider.exception")
    assert projection.code == "runtime.internal_error"
    assert projection.message == "请求暂时无法完成，请稍后重试。"


@pytest.mark.anyio
async def test_chat_json_unexpected_exception_is_safe(monkeypatch) -> None:
    def fail(*_args, **_kwargs):
        raise RuntimeError("SQL driver password=secret / C:\\private\\stack")

    monkeypatch.setattr(agent_dependency, "call_shopmind_agent", fail)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/chat",
            json={"message": "recommend a keyboard", "include_debug": True},
        )

    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "failed"
    assert body["runtime_error_code"] == "runtime.internal_error"
    assert "SQL driver" not in str(body)
    assert "secret" not in str(body)


@pytest.mark.anyio
async def test_chat_confirm_unexpected_exception_is_safe(monkeypatch) -> None:
    def fail(*_args, **_kwargs):
        raise RuntimeError("psycopg column=private_token traceback")

    monkeypatch.setattr(agent_dependency, "confirm_pending_action", fail)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/chat/confirm",
            json={
                "user_id": "user-1",
                "pending_action_id": "action-1",
                "confirmed": True,
                "include_debug": True,
            },
        )

    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "failed"
    assert body["pending_action_id"] == "action-1"
    assert body["runtime_error_code"] == "runtime.internal_error"
    assert "psycopg" not in str(body)
    assert "private_token" not in str(body)


@pytest.mark.anyio
async def test_json_and_sse_typed_failure_projection_match(monkeypatch) -> None:
    failure = {
        "answer": "private provider failure",
        "status": "failed",
        "tool_calls": [],
        "runtime_error_code": "version_conflict",
        "debug": {"error_message": "private provider failure"},
    }
    monkeypatch.setattr(agent_dependency, "call_shopmind_agent", lambda *_a, **_k: failure)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        json_response = await client.post(
            "/api/chat",
            json={"message": "retry", "include_debug": True},
        )
        sse_response = await client.post(
            "/api/chat/stream",
            json={"message": "retry", "include_debug": True},
        )

    json_body = json_response.json()
    assert json_body["runtime_error_code"] == "version_conflict"
    assert json_body["answer"] == "待确认动作版本已变化，请重新加载后再确认。"
    assert "private provider failure" not in str(json_body)
    assert '"runtime_error_code": "version_conflict"' in sse_response.text
    assert "待确认动作版本已变化，请重新加载后再确认。" in sse_response.text
    assert "private provider failure" not in sse_response.text


def test_public_exception_logging_keeps_bounded_internal_diagnostics(caplog) -> None:
    caplog.set_level(logging.INFO, logger="shopmind.observability")
    log_public_exception(
        "chat.test_boundary",
        RuntimeError("private provider password=secret"),
        thread_id="thread-1",
    )

    assert "chat.test_boundary" in caplog.text
    assert "RuntimeError" in caplog.text
    assert "password=<redacted>" in caplog.text
    assert "secret" not in caplog.text
