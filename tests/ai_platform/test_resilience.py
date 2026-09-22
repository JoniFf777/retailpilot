from datetime import datetime, timezone

import pytest

from app.ai_platform.contracts import ModelCandidate, ModelFailureCode, ModelOperation
from app.ai_platform.resilience import (
    AdmissionRejected,
    ModelGateway,
    ModelGatewayError,
    ModelInvocation,
    OperationAdmission,
    SharedAIBudget,
)
from app.runtime.coordination import LocalRuntimeCoordinationBackend


def candidate(candidate_id: str, priority: int) -> ModelCandidate:
    return ModelCandidate(
        candidate_id=candidate_id,
        operation=ModelOperation.PLANNER,
        provider="test",
        model=candidate_id,
        priority=priority,
    )


def test_operation_admission_releases_and_rejects_duplicate_capacity() -> None:
    backend = LocalRuntimeCoordinationBackend()
    admission = OperationAdmission(backend, max_concurrency=1, rate_limit=10)
    first = admission.acquire("planner", "user-1")
    with pytest.raises(AdmissionRejected):
        admission.acquire("planner", "user-1")
    assert first.release()
    assert admission.acquire("planner", "user-1").release()


def test_model_gateway_falls_back_before_first_token() -> None:
    gateway = ModelGateway([candidate("primary", 1), candidate("backup", 2)])
    calls: list[str] = []

    def invoke(model):
        calls.append(model.candidate_id)
        if model.candidate_id == "primary":
            raise ConnectionError()
        return ModelInvocation(value="ok", first_token_emitted=False)

    result = gateway.execute(ModelOperation.PLANNER, invoke)
    assert result.value == "ok"
    assert calls == ["primary", "backup"]


def test_model_gateway_does_not_fallback_after_stream_started() -> None:
    gateway = ModelGateway([candidate("primary", 1), candidate("backup", 2)])

    def invoke(model):
        if model.candidate_id == "primary":
            raise ModelGatewayError(ModelFailureCode.TOTAL_TIMEOUT, stream_started=True)
        return ModelInvocation(value="backup")

    with pytest.raises(ModelGatewayError) as error:
        gateway.execute(ModelOperation.PLANNER, invoke)
    assert error.value.stream_started is True


def test_gateway_health_opens_after_repeated_failures() -> None:
    gateway = ModelGateway([candidate("primary", 1)], failure_threshold=2)

    def invoke(_model):
        raise ConnectionError()

    for _ in range(2):
        with pytest.raises(ModelGatewayError):
            gateway.execute(ModelOperation.PLANNER, invoke)
    assert gateway.health()[0].state == "open"


def test_gateway_reports_each_attempt_to_observer():
    attempts = []
    gateway = ModelGateway([candidate("primary", 1)], attempt_observer=attempts.append)

    result = gateway.execute(
        ModelOperation.PLANNER,
        lambda _model: ModelInvocation(value="ok", duration_ms=3),
    )
    assert result.value == "ok"
    assert [attempt.status for attempt in attempts] == ["started", "succeeded"]


def test_gateway_retries_a_candidate_within_its_server_bound():
    attempts = []
    model = candidate("primary", 1).model_copy(update={"max_attempts": 2})
    gateway = ModelGateway([model], attempt_observer=attempts.append)
    calls = 0

    def invoke(_model):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TimeoutError()
        return ModelInvocation(value="ok")

    assert gateway.execute(ModelOperation.PLANNER, invoke).value == "ok"
    assert calls == 2
    assert [attempt.status for attempt in attempts] == [
        "started",
        "failed",
        "started",
        "succeeded",
    ]


def test_shared_budget_is_accounted_across_attempts():
    budget = SharedAIBudget(max_total_tokens=3)
    gateway = ModelGateway([candidate("primary", 1)], budget=budget)
    assert (
        gateway.execute(
            ModelOperation.PLANNER,
            lambda _model: ModelInvocation(
                value="ok", prompt_tokens=1, completion_tokens=2
            ),
        ).value
        == "ok"
    )
    assert budget.total_tokens == 3


def test_cancellation_stops_before_invocation():
    gateway = ModelGateway([candidate("primary", 1)], cancellation_check=lambda: True)
    with pytest.raises(ModelGatewayError) as error:
        gateway.execute(
            ModelOperation.PLANNER, lambda _model: ModelInvocation(value="bad")
        )
    assert error.value.code == ModelFailureCode.CANCELLED
