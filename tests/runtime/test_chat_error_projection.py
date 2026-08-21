from app.runtime import ErrorSource, RunError, RunResult, RunStatus
from app.services.pending_actions import PendingActionServiceError
from app.runtime.harness import ShopMindRuntimeHarness, run_result_to_legacy_response


def test_legacy_projection_sanitizes_failed_run_answer() -> None:
    result = RunResult(
        run_id="run-1",
        runtime_thread_id="thread-1",
        trace_id="trace-1",
        request_id="request-1",
        status=RunStatus.FAILED,
        answer="SQL table=private_users traceback",
        error=RunError(
            code="runtime.executor_exception",
            message="Runtime execution failed.",
            source=ErrorSource.AGENT,
        ),
        debug={"traceback": "private stack", "agent_steps": []},
    )

    projected = run_result_to_legacy_response(result, include_debug=True)

    assert projected["runtime_error_code"] == "runtime.executor_exception"
    assert projected["answer"] != "SQL table=private_users traceback"
    assert "traceback" not in str(projected)


def test_typed_domain_exception_keeps_safe_code_for_persisted_runtime_error() -> None:
    harness = ShopMindRuntimeHarness(session_factory=None)

    error = harness._as_runtime_error(
        PendingActionServiceError("version_conflict", "private database detail")
    )

    assert error.code == "version_conflict"
    assert error.message == "待确认动作版本已变化，请重新加载后再确认。"
    assert "private database detail" not in error.message
