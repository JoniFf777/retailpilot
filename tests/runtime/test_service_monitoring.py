from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest

from app.runtime import (
    RunOperation,
    RunRequest,
    RunResult,
    RunStatus,
    RunUsage,
    RuntimeServiceMonitor,
    ShopMindRuntimeHarness,
    evaluate_service_slo,
)


NOW = datetime(2026, 7, 26, 14, 0, tzinfo=timezone.utc)


def _result(
    status: RunStatus,
    *,
    usage: RunUsage | None = None,
) -> RunResult:
    return RunResult(
        run_id="private-run",
        runtime_thread_id="private-runtime-thread",
        trace_id="private-trace",
        request_id="private-request",
        user_id="private-user",
        client_thread_id="private-client-thread",
        status=status,
        answer="private answer",
        usage=usage or RunUsage(),
        completed_at=NOW,
    )


def test_monitor_accumulates_closed_bounded_metrics_without_identifiers() -> None:
    monitor = RuntimeServiceMonitor(
        latency_window_capacity=3,
        clock=lambda: NOW,
    )
    monitor.observe(
        _result(
            RunStatus.COMPLETED,
            usage=RunUsage(
                total_tokens=10,
                cost_usd=0.1,
                tool_call_count=1,
                step_count=2,
            ),
        ),
        operation=RunOperation.CHAT,
        duration_ms=100,
        replayed=True,
    )
    monitor.observe(
        _result(RunStatus.CONFIRMATION_REQUIRED),
        operation=RunOperation.CHAT,
        duration_ms=200,
    )
    monitor.observe(
        _result(RunStatus.CANCELLED),
        operation=RunOperation.CONFIRM_PENDING_ACTION,
        duration_ms=300,
    )
    monitor.observe_failure(
        operation=RunOperation.CONFIRM_PENDING_ACTION,
        duration_ms=1_000,
    )
    snapshot = monitor.snapshot()
    serialized = snapshot.model_dump_json()

    assert snapshot.status == "active"
    assert snapshot.runs_total == 4
    assert snapshot.chat_runs_total == 2
    assert snapshot.confirmation_runs_total == 2
    assert snapshot.completed_total == 1
    assert snapshot.confirmation_required_total == 1
    assert snapshot.cancelled_total == 1
    assert snapshot.failed_total == 1
    assert snapshot.replayed_total == 1
    assert snapshot.measured_token_runs_total == 1
    assert snapshot.total_tokens == 10
    assert snapshot.measured_cost_runs_total == 1
    assert snapshot.total_cost_usd == 0.1
    assert snapshot.tool_calls_total == 1
    assert snapshot.steps_total == 2
    assert snapshot.latency_observations_total == 4
    assert snapshot.latency_window_capacity == 3
    assert snapshot.latency_window_runs == 3
    assert snapshot.slo_window_eligible_runs == 2
    assert snapshot.slo_window_successful_runs == 1
    assert snapshot.latency_p50_ms == 300
    assert snapshot.latency_p95_ms == 1_000
    assert snapshot.latency_max_ms == 1_000
    assert snapshot.last_status == "failed"
    assert snapshot.last_observed_at == NOW
    for private_value in (
        "private-run",
        "private-runtime-thread",
        "private-trace",
        "private-request",
        "private-user",
        "private-client-thread",
        "private answer",
    ):
        assert private_value not in serialized


def test_monitor_is_thread_safe_and_latency_window_is_bounded() -> None:
    monitor = RuntimeServiceMonitor(
        latency_window_capacity=10,
        clock=lambda: NOW,
    )
    result = _result(RunStatus.COMPLETED)

    def observe(index: int) -> None:
        monitor.observe(
            result,
            operation=RunOperation.CHAT,
            duration_ms=float(index),
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(observe, range(1, 101)))
    snapshot = monitor.snapshot()

    assert snapshot.runs_total == 100
    assert snapshot.completed_total == 100
    assert snapshot.latency_observations_total == 100
    assert snapshot.latency_window_capacity == 10
    assert snapshot.latency_window_runs == 10
    assert snapshot.latency_p95_ms is not None
    assert snapshot.latency_max_ms is not None


def test_slo_reports_insufficient_met_and_breached_states() -> None:
    idle = RuntimeServiceMonitor(clock=lambda: NOW).snapshot()
    insufficient = evaluate_service_slo(idle, minimum_runs=5)

    monitor = RuntimeServiceMonitor(clock=lambda: NOW)
    for duration in (10, 20, 30, 40):
        monitor.observe(
            _result(RunStatus.COMPLETED),
            operation=RunOperation.CHAT,
            duration_ms=duration,
        )
    monitor.observe_failure(
        operation=RunOperation.CHAT,
        duration_ms=50,
    )
    monitor.observe(
        _result(RunStatus.CANCELLED),
        operation=RunOperation.CHAT,
        duration_ms=5_000,
    )
    metrics = monitor.snapshot()
    met = evaluate_service_slo(
        metrics,
        minimum_runs=5,
        success_rate_target=0.8,
        p95_latency_target_ms=5_000,
    )
    breached = evaluate_service_slo(
        metrics,
        minimum_runs=5,
        success_rate_target=0.9,
        p95_latency_target_ms=100,
    )

    assert insufficient.status == "insufficient_data"
    assert {check.status for check in insufficient.checks} == {
        "insufficient_data"
    }
    assert met.status == "met"
    assert met.eligible_runs_total == 5
    assert met.successful_runs_total == 4
    assert met.observed_success_rate == 0.8
    assert {check.status for check in met.checks} == {"met"}
    assert breached.status == "breached"
    assert [check.status for check in breached.checks] == [
        "met",
        "breached",
        "breached",
    ]


def test_harness_observes_each_terminal_request_exactly_once() -> None:
    monitor = RuntimeServiceMonitor(clock=lambda: NOW)
    harness = ShopMindRuntimeHarness(None, service_monitor=monitor)
    request = RunRequest(
        operation=RunOperation.CHAT,
        user_id="private-harness-user",
        input_text="private harness message",
    )

    completed = harness.run(
        request,
        lambda _context: {
            "answer": "ok",
            "status": "completed",
            "tool_calls": [],
        },
    )
    failed = harness.run(
        request.model_copy(update={"request_id": "failure-request"}),
        lambda _context: (_ for _ in ()).throw(
            RuntimeError("private provider error")
        ),
        raise_on_error=False,
    )
    with pytest.raises(RuntimeError, match="private raised error"):
        harness.run(
            request.model_copy(update={"request_id": "raised-request"}),
            lambda _context: (_ for _ in ()).throw(
                RuntimeError("private raised error")
            ),
        )
    snapshot = monitor.snapshot()

    assert completed.status == RunStatus.COMPLETED
    assert failed.status == RunStatus.FAILED
    assert snapshot.runs_total == 3
    assert snapshot.completed_total == 1
    assert snapshot.failed_total == 2
    assert snapshot.chat_runs_total == 3
    assert "private" not in snapshot.model_dump_json()


def test_monitoring_failure_never_changes_harness_result() -> None:
    class UnavailableMonitor:
        def observe(self, *args, **kwargs):
            raise RuntimeError("private metrics sink")

        def observe_failure(self, *args, **kwargs):
            raise RuntimeError("private metrics sink")

    harness = ShopMindRuntimeHarness(
        None,
        service_monitor=UnavailableMonitor(),
    )
    result = harness.run(
        RunRequest(operation=RunOperation.CHAT, user_id="private-user"),
        lambda _context: {
            "answer": "ok",
            "status": "completed",
            "tool_calls": [],
        },
    )

    assert result.status == RunStatus.COMPLETED
