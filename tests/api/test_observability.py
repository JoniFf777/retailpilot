"""HTTP correlation and safe structured-log coverage."""

from __future__ import annotations

import json
import logging
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.routes import health as health_route
from app.api.routes.health import get_outbox_health_report
from app.core.logging import log_event
from app.api.middleware import CorrelationIdMiddleware
from app.main import app


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_correlation_id_is_echoed_and_generated_when_missing() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        supplied = await client.get(
            "/api/health",
            headers={"X-Correlation-ID": "demo-correlation-001"},
        )
        generated = await client.get("/api/health")

    assert supplied.status_code == 200
    assert supplied.headers["X-Correlation-ID"] == "demo-correlation-001"
    assert generated.status_code == 200
    assert generated.headers["X-Correlation-ID"]
    assert generated.headers["X-Correlation-ID"] != "demo-correlation-001"


@pytest.mark.anyio
async def test_invalid_or_oversized_correlation_id_is_replaced() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/health",
            headers={"X-Correlation-ID": "bad value with spaces"},
        )
        oversized = await client.get(
            "/api/health",
            headers={"X-Correlation-ID": "x" * 129},
        )

    assert response.headers["X-Correlation-ID"] != "bad value with spaces"
    assert oversized.headers["X-Correlation-ID"] != "x" * 129
    assert len(oversized.headers["X-Correlation-ID"]) == 36


@pytest.mark.anyio
async def test_http_log_keeps_correlation_and_request_trace_ids(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="shopmind.observability")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/health",
            headers={"X-Correlation-ID": "request-correlation-7"},
        )

    completed = [
        json.loads(record.getMessage())
        for record in caplog.records
        if record.name == "shopmind.observability"
        and json.loads(record.getMessage()).get("event") == "http.request.completed"
    ]
    assert response.status_code == 200
    assert completed
    payload = completed[-1]
    assert payload["correlation_id"] == "request-correlation-7"
    assert payload["request_id"]
    assert payload["trace_id"]
    assert payload["status"] == 200
    assert payload["duration_ms"] >= 0


@pytest.mark.anyio
async def test_http_middleware_never_logs_raw_unexpected_exception(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def raising_app(scope, receive, send) -> None:
        raise RuntimeError("failed for alice@example.com payment private-ref")

    caplog.set_level(logging.INFO, logger="shopmind.observability")
    middleware = CorrelationIdMiddleware(raising_app)
    async with AsyncClient(
        transport=ASGITransport(app=middleware, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.get("/unexpected")

    failed = [
        json.loads(record.getMessage())
        for record in caplog.records
        if record.name == "shopmind.observability"
        and json.loads(record.getMessage()).get("event") == "http.request.failed"
    ]
    assert response.status_code == 500
    assert failed
    payload = failed[-1]
    serialized = json.dumps(payload, ensure_ascii=False)
    assert payload["error_class"] == "RuntimeError"
    assert payload["error_code"] == "unexpected_http_error"
    assert payload["error_message"] == "Unexpected HTTP request failure."
    assert "alice@example.com" not in serialized
    assert "private-ref" not in serialized
    assert "failed for alice@example.com payment private-ref" not in serialized


def test_structured_log_is_json_and_redacts_non_allowlisted_fields(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="shopmind.observability")
    log_event(
        "payment.provider_outcome",
        order_id="order-1",
        payment_attempt_id="attempt-1",
        status="succeeded",
        error_message=(
            "user_id=alice@example.com payment_method_ref=private-ref "
            "idempotency_key=secret checkout_token=secret request_hash=secret"
        ),
        checkout_token="secret-token",
        payload={"card": "never-log"},
    )

    record = next(record for record in caplog.records if record.name == "shopmind.observability")
    payload = json.loads(record.getMessage())
    assert payload["event"] == "payment.provider_outcome"
    assert payload["order_id"] == "order-1"
    assert "checkout_token" not in payload
    assert "payload" not in payload
    assert "alice@example.com" not in payload["error_message"]
    assert "private-ref" not in payload["error_message"]
    assert "secret" not in payload["error_message"]


def test_outbox_health_is_optional_and_does_not_fail_when_publisher_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeSession:
        def close(self) -> None:
            pass

    settings = SimpleNamespace(shopmind_outbox_enabled=False)
    monkeypatch.setattr(
        "app.api.routes.health.get_outbox_health_snapshot",
        lambda _session: {
            "pending": 2,
            "publishing": 0,
            "published": 4,
            "dead_letter": 1,
            "oldest_pending_seconds": 12.5,
            "pending_truncated": False,
            "publishing_truncated": False,
            "published_truncated": False,
            "dead_letter_truncated": False,
        },
    )

    report = get_outbox_health_report(
        settings=settings,
        session_factory=FakeSession,
    )

    assert report["status"] == "disabled"
    assert report["publisher_enabled"] is False
    assert report["pending"] == 2
    assert report["dead_letter"] == 1


@pytest.mark.anyio
async def test_outbox_health_report_is_unavailable_without_affecting_core_readiness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        health_route,
        "get_deployment_readiness_health_report",
        lambda **_kwargs: {"status": "ready", "ready": True},
    )
    monkeypatch.setattr(
        health_route,
        "get_outbox_health_report",
        lambda **_kwargs: {
            "status": "unavailable",
            "publisher_enabled": True,
            "pending": None,
            "publishing": None,
            "published": None,
            "dead_letter": None,
            "oldest_pending_seconds": None,
            "error_code": "outbox_snapshot_unavailable",
        },
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/health/readiness")
    assert response.status_code == 200
    body = response.json()
    assert body["ready"] is True
    assert body["outbox"]["status"] == "unavailable"
