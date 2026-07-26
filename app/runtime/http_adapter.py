"""Server-owned HTTPS transport for typed specialist Agent tasks."""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlsplit

import httpx
from pydantic import ValidationError

from .adapters import (
    AgentAdapterError,
    AgentTransportError,
    _validate_adapter_task,
)
from .contracts import (
    AgentResult,
    AgentTask,
    AgentTransportFailureCode,
    RunUsage,
)


_DEFAULT_TIMEOUT_SECONDS = 10.0
_DEFAULT_MAX_RESPONSE_BYTES = 1_048_576
_UNAVAILABLE_STATUS_CODES = frozenset({429, 500, 502, 503})
_TIMEOUT_STATUS_CODES = frozenset({408, 504})


def _normalize_allowed_hosts(hosts: frozenset[str]) -> frozenset[str]:
    normalized: set[str] = set()
    for host in hosts:
        if (
            not isinstance(host, str)
            or not host
            or host != host.strip()
            or "://" in host
            or "/" in host
        ):
            raise AgentAdapterError(
                "HTTP Agent adapters require normalized allowed HTTPS hosts."
            )
        normalized.add(host.lower())
    if not normalized:
        raise AgentAdapterError(
            "HTTP Agent adapters require at least one allowed HTTPS host."
        )
    return frozenset(normalized)


@dataclass(frozen=True)
class HttpAgentAdapter:
    """Invoke one trusted specialist endpoint through a bounded HTTPS client.

    Endpoint selection and credentials are constructor-only server configuration;
    no request field can choose a destination or override transport policy.
    """

    agent_name: str
    endpoint_url: str
    allowed_https_hosts: frozenset[str]
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS
    max_response_bytes: int = _DEFAULT_MAX_RESPONSE_BYTES
    authorization_bearer_token: str | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    client: httpx.Client | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.agent_name, str)
            or not self.agent_name
            or self.agent_name != self.agent_name.strip()
        ):
            raise AgentAdapterError(
                "HTTP Agent adapters require a normalized agent_name."
            )
        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, (int, float))
            or not 0 < self.timeout_seconds <= 30
        ):
            raise AgentAdapterError(
                "HTTP Agent adapter timeout must be above zero and at most 30 seconds."
            )
        if (
            isinstance(self.max_response_bytes, bool)
            or not isinstance(self.max_response_bytes, int)
            or not 1 <= self.max_response_bytes <= _DEFAULT_MAX_RESPONSE_BYTES
        ):
            raise AgentAdapterError(
                "HTTP Agent adapter response limit must be between 1 and 1048576 bytes."
            )
        if self.authorization_bearer_token is not None and (
            not isinstance(self.authorization_bearer_token, str)
            or not self.authorization_bearer_token.strip()
            or self.authorization_bearer_token
            != self.authorization_bearer_token.strip()
        ):
            raise AgentAdapterError(
                "HTTP Agent adapter bearer tokens must be non-empty normalized strings."
            )
        if self.client is not None and not isinstance(self.client, httpx.Client):
            raise AgentAdapterError(
                "HTTP Agent adapters require an httpx.Client transport."
            )

        allowed_hosts = _normalize_allowed_hosts(self.allowed_https_hosts)
        parsed = urlsplit(self.endpoint_url)
        if (
            parsed.scheme.lower() != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise AgentAdapterError(
                "HTTP Agent adapter endpoints require a fixed HTTPS URL without "
                "credentials, query parameters, or fragments."
            )
        if parsed.hostname.lower() not in allowed_hosts:
            raise AgentAdapterError(
                "HTTP Agent adapter endpoint host is not server-allowed."
            )
        object.__setattr__(self, "allowed_https_hosts", allowed_hosts)

    def invoke(self, task: AgentTask) -> AgentResult:
        _validate_adapter_task(self.agent_name, task)
        if self.client is not None:
            return self._invoke_with_client(self.client, task)
        with httpx.Client(follow_redirects=False) as client:
            return self._invoke_with_client(client, task)

    def _invoke_with_client(
        self,
        client: httpx.Client,
        task: AgentTask,
    ) -> AgentResult:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-ShopMind-Run-Id": task.run_id,
            "X-ShopMind-Task-Id": task.task_id,
            "X-ShopMind-Trace-Id": task.trace_id,
        }
        if task.idempotency_key is not None:
            headers["Idempotency-Key"] = task.idempotency_key
        if self.authorization_bearer_token is not None:
            headers["Authorization"] = (
                f"Bearer {self.authorization_bearer_token}"
            )

        try:
            with client.stream(
                "POST",
                self.endpoint_url,
                content=task.model_dump_json().encode("utf-8"),
                headers=headers,
                timeout=httpx.Timeout(float(self.timeout_seconds)),
                follow_redirects=False,
            ) as response:
                self._raise_for_status(response.status_code)
                content_length = response.headers.get("Content-Length")
                if content_length is not None:
                    try:
                        declared_size = int(content_length)
                    except ValueError:
                        self._raise_protocol_error()
                    if declared_size > self.max_response_bytes:
                        self._raise_protocol_error()

                payload = bytearray()
                for chunk in response.iter_bytes():
                    payload.extend(chunk)
                    if len(payload) > self.max_response_bytes:
                        self._raise_protocol_error()
        except AgentTransportError:
            raise
        except httpx.TimeoutException as exc:
            raise self._transport_error(
                AgentTransportFailureCode.TIMEOUT,
                retriable=True,
            ) from exc
        except httpx.RequestError as exc:
            raise self._transport_error(
                AgentTransportFailureCode.UNAVAILABLE,
                retriable=True,
            ) from exc

        try:
            result = AgentResult.model_validate_json(bytes(payload))
        except (ValidationError, ValueError) as exc:
            raise self._transport_error(
                AgentTransportFailureCode.PROTOCOL_ERROR,
                retriable=False,
            ) from exc
        if result.task_id != task.task_id:
            self._raise_protocol_error()
        return result

    @staticmethod
    def _transport_error(
        failure_code: AgentTransportFailureCode,
        *,
        retriable: bool,
    ) -> AgentTransportError:
        return AgentTransportError(
            failure_code,
            retriable=retriable,
            usage=RunUsage(step_count=1),
        )

    def _raise_for_status(self, status_code: int) -> None:
        if 200 <= status_code < 300:
            return
        if status_code in _TIMEOUT_STATUS_CODES:
            raise self._transport_error(
                AgentTransportFailureCode.TIMEOUT,
                retriable=True,
            )
        if status_code in _UNAVAILABLE_STATUS_CODES:
            raise self._transport_error(
                AgentTransportFailureCode.UNAVAILABLE,
                retriable=True,
            )
        self._raise_protocol_error()

    def _raise_protocol_error(self) -> None:
        raise self._transport_error(
            AgentTransportFailureCode.PROTOCOL_ERROR,
            retriable=False,
        )


__all__ = ["HttpAgentAdapter"]
