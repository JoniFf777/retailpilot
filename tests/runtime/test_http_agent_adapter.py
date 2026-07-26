import json

import httpx
import pytest

from app.runtime import (
    AgentAdapter,
    AgentAdapterError,
    AgentAdapterRegistry,
    AgentResult,
    AgentTask,
    AgentTaskRetryOwner,
    AgentTaskRetryPolicy,
    AgentTaskStatus,
    AgentTransportError,
    AgentTransportFailureCode,
    DelegationBudgetGuard,
    HttpAgentAdapter,
    PolicyEnforcedAgentAdapter,
    RunUsage,
    build_agent_task_idempotency_key,
)


ENDPOINT = "https://specialists.internal.example/v1/tasks"
ALLOWED_HOSTS = frozenset({"specialists.internal.example"})


def make_task(*, task_id: str = "task-1") -> AgentTask:
    retry_policy = AgentTaskRetryPolicy(
        owner=AgentTaskRetryOwner.PLAN_EXECUTOR,
        max_attempts=2,
        retryable_failure_codes={AgentTransportFailureCode.UNAVAILABLE},
    )
    return AgentTask(
        task_id=task_id,
        run_id="run-1",
        sender="supervisor",
        recipient="rag_agent",
        intent="policy_read",
        input_data={"query": "return policy"},
        trace_id="trace-1",
        idempotency_key=build_agent_task_idempotency_key("run-1", task_id),
        retry_policy=retry_policy,
    )


def completed_response(task: AgentTask) -> httpx.Response:
    result = AgentResult(
        task_id=task.task_id,
        status=AgentTaskStatus.COMPLETED,
        output_data={"answer": "30 days"},
        usage=RunUsage(total_tokens=12, step_count=1),
    )
    return httpx.Response(
        200,
        headers={"Content-Type": "application/json"},
        content=result.model_dump_json().encode("utf-8"),
    )


def make_adapter(handler, **overrides) -> HttpAgentAdapter:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    values = {
        "agent_name": "rag_agent",
        "endpoint_url": ENDPOINT,
        "allowed_https_hosts": ALLOWED_HOSTS,
        "client": client,
    }
    values.update(overrides)
    return HttpAgentAdapter(**values)


def test_http_adapter_sends_typed_task_and_trusted_headers() -> None:
    task = make_task()
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return completed_response(task)

    adapter = make_adapter(
        handler,
        authorization_bearer_token="server-secret-token",
    )

    result = adapter.invoke(task)

    request = captured["request"]
    assert isinstance(adapter, AgentAdapter)
    assert request.method == "POST"
    assert str(request.url) == ENDPOINT
    assert json.loads(request.content)["task_id"] == "task-1"
    assert request.headers["x-shopmind-run-id"] == "run-1"
    assert request.headers["x-shopmind-task-id"] == "task-1"
    assert request.headers["x-shopmind-trace-id"] == "trace-1"
    assert request.headers["idempotency-key"] == task.idempotency_key
    assert request.headers["authorization"] == "Bearer server-secret-token"
    assert result.output_data == {"answer": "30 days"}
    assert "server-secret-token" not in repr(adapter)
    adapter.client.close()


@pytest.mark.parametrize(
    ("endpoint_url", "allowed_hosts", "message"),
    [
        (
            "http://specialists.internal.example/v1/tasks",
            ALLOWED_HOSTS,
            "fixed HTTPS URL",
        ),
        (
            "https://user:password@specialists.internal.example/v1/tasks",
            ALLOWED_HOSTS,
            "fixed HTTPS URL",
        ),
        (
            f"{ENDPOINT}?target=other",
            ALLOWED_HOSTS,
            "fixed HTTPS URL",
        ),
        (
            ENDPOINT,
            frozenset({"other.internal.example"}),
            "not server-allowed",
        ),
    ],
)
def test_http_adapter_rejects_untrusted_endpoint_configuration(
    endpoint_url,
    allowed_hosts,
    message,
) -> None:
    with pytest.raises(AgentAdapterError, match=message):
        HttpAgentAdapter(
            agent_name="rag_agent",
            endpoint_url=endpoint_url,
            allowed_https_hosts=allowed_hosts,
        )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"agent_name": " rag_agent"}, "normalized agent_name"),
        ({"allowed_https_hosts": frozenset()}, "at least one"),
        ({"timeout_seconds": 0}, "timeout"),
        ({"timeout_seconds": 31}, "timeout"),
        ({"max_response_bytes": 0}, "response limit"),
        ({"max_response_bytes": 1_048_577}, "response limit"),
        ({"authorization_bearer_token": " "}, "bearer tokens"),
    ],
)
def test_http_adapter_rejects_invalid_bounded_configuration(
    overrides,
    message,
) -> None:
    values = {
        "agent_name": "rag_agent",
        "endpoint_url": ENDPOINT,
        "allowed_https_hosts": ALLOWED_HOSTS,
    }
    values.update(overrides)
    with pytest.raises(AgentAdapterError, match=message):
        HttpAgentAdapter(**values)


@pytest.mark.parametrize(
    ("status_code", "failure_code", "retriable"),
    [
        (408, AgentTransportFailureCode.TIMEOUT, True),
        (504, AgentTransportFailureCode.TIMEOUT, True),
        (429, AgentTransportFailureCode.UNAVAILABLE, True),
        (500, AgentTransportFailureCode.UNAVAILABLE, True),
        (502, AgentTransportFailureCode.UNAVAILABLE, True),
        (503, AgentTransportFailureCode.UNAVAILABLE, True),
        (302, AgentTransportFailureCode.PROTOCOL_ERROR, False),
        (400, AgentTransportFailureCode.PROTOCOL_ERROR, False),
    ],
)
def test_http_adapter_maps_statuses_to_sanitized_transport_failures(
    status_code,
    failure_code,
    retriable,
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, content=b"private upstream details")

    adapter = make_adapter(handler)
    with pytest.raises(AgentTransportError) as caught:
        adapter.invoke(make_task())

    assert caught.value.failure_code == failure_code
    assert caught.value.retriable is retriable
    assert caught.value.usage == RunUsage(step_count=1)
    assert "private" not in str(caught.value)
    assert ENDPOINT not in str(caught.value)
    adapter.client.close()


@pytest.mark.parametrize(
    ("exception_factory", "failure_code"),
    [
        (
            lambda request: httpx.ReadTimeout(
                "private timeout detail",
                request=request,
            ),
            AgentTransportFailureCode.TIMEOUT,
        ),
        (
            lambda request: httpx.ConnectError(
                "private connection detail",
                request=request,
            ),
            AgentTransportFailureCode.UNAVAILABLE,
        ),
    ],
)
def test_http_adapter_maps_client_failures_without_leaking_details(
    exception_factory,
    failure_code,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise exception_factory(request)

    adapter = make_adapter(handler)
    with pytest.raises(AgentTransportError) as caught:
        adapter.invoke(make_task())

    assert caught.value.failure_code == failure_code
    assert caught.value.retriable is True
    assert "private" not in str(caught.value)
    adapter.client.close()


@pytest.mark.parametrize(
    "response_factory",
    [
        lambda task: httpx.Response(200, content=b"not-json"),
        lambda task: httpx.Response(
            200,
            content=AgentResult(
                task_id="wrong-task",
                status=AgentTaskStatus.COMPLETED,
            ).model_dump_json().encode("utf-8"),
        ),
        lambda task: httpx.Response(
            200,
            headers={"Content-Length": "20"},
            content=b"x" * 20,
        ),
    ],
)
def test_http_adapter_rejects_invalid_or_oversized_responses(
    response_factory,
) -> None:
    task = make_task()

    def handler(_request: httpx.Request) -> httpx.Response:
        return response_factory(task)

    adapter = make_adapter(handler, max_response_bytes=10)
    with pytest.raises(AgentTransportError) as caught:
        adapter.invoke(task)

    assert caught.value.failure_code == AgentTransportFailureCode.PROTOCOL_ERROR
    assert caught.value.retriable is False
    adapter.client.close()


def test_http_adapter_runs_under_required_policy_registry() -> None:
    task = make_task()

    def handler(_request: httpx.Request) -> httpx.Response:
        return completed_response(task)

    transport = make_adapter(handler)
    adapter = PolicyEnforcedAgentAdapter(
        adapter=transport,
        delegation_guard=DelegationBudgetGuard(),
    )
    registry = AgentAdapterRegistry([adapter], require_policy=True)

    result = registry.invoke(task)

    assert result.status == AgentTaskStatus.COMPLETED
    assert adapter.delegation_guard.usage_snapshot("run-1") == RunUsage(
        total_tokens=12,
        step_count=1,
    )
    transport.client.close()
