"""Compact policy-preserving client for the ShopMind V6 reference API."""

from __future__ import annotations

import argparse
import ipaddress
import json
import sys
from collections.abc import Iterator, Sequence
from typing import TypeVar
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ValidationError

from app.governance import OwnerDataSnapshot, OwnerRunInspection
from app.runtime import AgentEvent
from app.schemas.chat import ChatRequest, ChatResponse, ConfirmChatRequest
from app.schemas.owner_data import OwnerDataInspectRequest, OwnerRunInspectRequest


DEFAULT_BASE_URL = "http://127.0.0.1:8000/api"
DEFAULT_TIMEOUT_SECONDS = 15.0
MAX_TIMEOUT_SECONDS = 30.0
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_SSE_EVENT_BYTES = 256 * 1024
MAX_SSE_EVENTS = 1_000

ModelT = TypeVar("ModelT", bound=BaseModel)


class ReferenceClientError(RuntimeError):
    """Closed client failure that never carries a URL or response body."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _is_loopback(hostname: str) -> bool:
    if hostname.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def validate_base_url(value: str) -> str:
    """Allow local HTTP or credential-free HTTPS without query selectors."""

    try:
        parsed = urlsplit(value.strip())
    except ValueError as exc:
        raise ValueError("Reference client base URL is invalid.") from exc
    hostname = parsed.hostname or ""
    if (
        parsed.scheme not in {"http", "https"}
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Reference client base URL is invalid.")
    if parsed.scheme == "http" and not _is_loopback(hostname):
        raise ValueError("Reference client remote endpoints require HTTPS.")
    return value.strip().rstrip("/")


def _idempotency_headers(value: str | None) -> dict[str, str]:
    if value is None:
        return {}
    normalized = value.strip()
    if not 1 <= len(normalized) <= 256:
        raise ReferenceClientError("idempotency_key_invalid")
    return {"Idempotency-Key": normalized}


class ShopMindReferenceClient:
    """Use only public ShopMind endpoints; never access internal persistence."""

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.BaseTransport | None = None,
        max_response_bytes: int = MAX_RESPONSE_BYTES,
        max_sse_events: int = MAX_SSE_EVENTS,
    ) -> None:
        if not 0 < timeout_seconds <= MAX_TIMEOUT_SECONDS:
            raise ValueError("Reference client timeout is out of bounds.")
        if not 1 <= max_response_bytes <= MAX_RESPONSE_BYTES:
            raise ValueError("Reference client response limit is out of bounds.")
        if not 1 <= max_sse_events <= MAX_SSE_EVENTS:
            raise ValueError("Reference client event limit is out of bounds.")
        self._max_response_bytes = max_response_bytes
        self._max_sse_events = max_sse_events
        self._client = httpx.Client(
            base_url=validate_base_url(base_url),
            timeout=timeout_seconds,
            follow_redirects=False,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "ShopMindReferenceClient":
        return self

    def __exit__(self, *_args) -> None:
        self.close()

    def chat(
        self,
        *,
        message: str,
        user_id: str | None,
        thread_id: str | None,
        include_debug: bool = True,
        idempotency_key: str | None = None,
    ) -> ChatResponse:
        request = ChatRequest(
            message=message,
            user_id=user_id,
            thread_id=thread_id,
            include_debug=include_debug,
        )
        return self._post_json(
            "/chat",
            request.model_dump(mode="json"),
            ChatResponse,
            headers=_idempotency_headers(idempotency_key),
        )

    def stream_chat(
        self,
        *,
        message: str,
        user_id: str | None,
        thread_id: str | None,
        include_debug: bool = True,
        idempotency_key: str | None = None,
    ) -> Iterator[AgentEvent]:
        request = ChatRequest(
            message=message,
            user_id=user_id,
            thread_id=thread_id,
            include_debug=include_debug,
        )
        headers = {
            "Accept": "text/event-stream",
            **_idempotency_headers(idempotency_key),
        }
        try:
            with self._client.stream(
                "POST",
                "/chat/stream",
                json=request.model_dump(mode="json"),
                headers=headers,
            ) as response:
                self._assert_success(response, "text/event-stream")
                yield from self._parse_sse(response)
        except ReferenceClientError:
            raise
        except httpx.HTTPError as exc:
            raise ReferenceClientError("transport_unavailable") from exc
        except (ValidationError, ValueError, json.JSONDecodeError) as exc:
            raise ReferenceClientError("stream_protocol_invalid") from exc

    def confirm(
        self,
        *,
        user_id: str,
        pending_action_id: str,
        confirmed: bool,
        thread_id: str | None,
        updated_arguments: dict | None = None,
        include_debug: bool = True,
        idempotency_key: str | None = None,
    ) -> ChatResponse:
        request = ConfirmChatRequest(
            user_id=user_id,
            pending_action_id=pending_action_id,
            confirmed=confirmed,
            thread_id=thread_id,
            updated_arguments=updated_arguments,
            include_debug=include_debug,
        )
        return self._post_json(
            "/chat/confirm",
            request.model_dump(mode="json", exclude_none=True),
            ChatResponse,
            headers=_idempotency_headers(idempotency_key),
        )

    def inspect_memory(
        self,
        *,
        user_id: str,
        memory_limit: int = 50,
    ) -> OwnerDataSnapshot:
        request = OwnerDataInspectRequest(
            user_id=user_id,
            memory_limit=memory_limit,
        )
        return self._post_json(
            "/owner-data/inspect",
            request.model_dump(mode="json"),
            OwnerDataSnapshot,
        )

    def inspect_run(
        self,
        *,
        user_id: str,
        run_id: str | None = None,
        trace_id: str | None = None,
        event_limit: int = 50,
    ) -> OwnerRunInspection:
        request = OwnerRunInspectRequest(
            user_id=user_id,
            run_id=run_id,
            trace_id=trace_id,
            event_limit=event_limit,
        )
        return self._post_json(
            "/owner-data/runs/inspect",
            request.model_dump(mode="json", exclude_none=True),
            OwnerRunInspection,
        )

    def _post_json(
        self,
        path: str,
        payload: dict,
        response_model: type[ModelT],
        *,
        headers: dict[str, str] | None = None,
    ) -> ModelT:
        try:
            with self._client.stream(
                "POST",
                path,
                json=payload,
                headers=headers,
            ) as response:
                self._assert_success(response, "application/json")
                content = self._read_bounded(response)
            return response_model.model_validate_json(content)
        except ReferenceClientError:
            raise
        except httpx.HTTPError as exc:
            raise ReferenceClientError("transport_unavailable") from exc
        except (ValidationError, ValueError, json.JSONDecodeError) as exc:
            raise ReferenceClientError("response_protocol_invalid") from exc

    def _assert_success(
        self,
        response: httpx.Response,
        expected_content_type: str,
    ) -> None:
        if response.is_redirect:
            raise ReferenceClientError("redirect_rejected")
        if response.status_code >= 300:
            raise ReferenceClientError(
                f"request_failed_{response.status_code}"
            )
        content_type = response.headers.get("content-type", "").lower()
        if expected_content_type not in content_type:
            raise ReferenceClientError("content_type_invalid")

    def _read_bounded(self, response: httpx.Response) -> bytes:
        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_bytes():
            total += len(chunk)
            if total > self._max_response_bytes:
                raise ReferenceClientError("response_too_large")
            chunks.append(chunk)
        return b"".join(chunks)

    def _parse_sse(self, response: httpx.Response) -> Iterator[AgentEvent]:
        event_type: str | None = None
        event_id: str | None = None
        data_lines: list[str] = []
        event_bytes = 0
        event_count = 0
        last_sequence = 0

        def finish_event() -> AgentEvent | None:
            nonlocal event_type, event_id, data_lines, event_bytes
            if event_type is None and event_id is None and not data_lines:
                event_bytes = 0
                return None
            if event_type is None or event_id is None or not data_lines:
                raise ReferenceClientError("stream_protocol_invalid")
            if event_bytes > MAX_SSE_EVENT_BYTES:
                raise ReferenceClientError("stream_event_too_large")
            event = AgentEvent.model_validate_json("\n".join(data_lines))
            if event.event_type != event_type or event.sequence != int(event_id):
                raise ReferenceClientError("stream_protocol_invalid")
            event_type = None
            event_id = None
            data_lines = []
            event_bytes = 0
            return event

        for line in response.iter_lines():
            event_bytes += len(line.encode("utf-8"))
            if event_bytes > MAX_SSE_EVENT_BYTES:
                raise ReferenceClientError("stream_event_too_large")
            if line == "":
                event = finish_event()
                if event is None:
                    continue
                event_count += 1
                if (
                    event_count > self._max_sse_events
                    or event.sequence <= last_sequence
                ):
                    raise ReferenceClientError("stream_bounds_exceeded")
                last_sequence = event.sequence
                yield event
                continue
            if line.startswith(":"):
                continue
            field, separator, value = line.partition(":")
            if not separator:
                raise ReferenceClientError("stream_protocol_invalid")
            value = value[1:] if value.startswith(" ") else value
            if field == "event":
                event_type = value
            elif field == "id":
                event_id = value
            elif field == "data":
                data_lines.append(value)

        event = finish_event()
        if event is not None:
            event_count += 1
            if (
                event_count > self._max_sse_events
                or event.sequence <= last_sequence
            ):
                raise ReferenceClientError("stream_bounds_exceeded")
            yield event


def _positive_timeout(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("timeout must be numeric") from exc
    if not 0 < parsed <= MAX_TIMEOUT_SECONDS:
        raise argparse.ArgumentTypeError("timeout must be within (0, 30]")
    return parsed


def _json_object(value: str | None) -> dict | None:
    if value is None:
        return None
    if len(value.encode("utf-8")) > 8_192:
        raise ReferenceClientError("updated_arguments_too_large")
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ReferenceClientError("updated_arguments_invalid") from exc
    if not isinstance(parsed, dict):
        raise ReferenceClientError("updated_arguments_invalid")
    return parsed


def _add_chat_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--message", required=True)
    parser.add_argument("--user-id")
    parser.add_argument("--thread-id")
    parser.add_argument("--idempotency-key")
    parser.add_argument("--no-debug", action="store_true")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Use only ShopMind public APIs; trusted ingress remains "
            "responsible for production identity headers."
        )
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument(
        "--timeout-seconds",
        default=DEFAULT_TIMEOUT_SECONDS,
        type=_positive_timeout,
    )
    commands = parser.add_subparsers(dest="command", required=True)

    chat = commands.add_parser("chat")
    _add_chat_arguments(chat)
    stream = commands.add_parser("stream")
    _add_chat_arguments(stream)

    confirm = commands.add_parser("confirm")
    confirm.add_argument("--user-id", required=True)
    confirm.add_argument("--thread-id")
    confirm.add_argument("--pending-action-id", required=True)
    decision = confirm.add_mutually_exclusive_group(required=True)
    decision.add_argument("--approve", action="store_true")
    decision.add_argument("--cancel", action="store_true")
    confirm.add_argument("--updated-arguments-json")
    confirm.add_argument("--idempotency-key")
    confirm.add_argument("--no-debug", action="store_true")

    memory = commands.add_parser("memory")
    memory.add_argument("--user-id", required=True)
    memory.add_argument("--limit", type=int, default=50)

    run = commands.add_parser("run")
    run.add_argument("--user-id", required=True)
    selector = run.add_mutually_exclusive_group(required=True)
    selector.add_argument("--run-id")
    selector.add_argument("--trace-id")
    run.add_argument("--event-limit", type=int, default=50)
    return parser


def _print_model(model: BaseModel) -> None:
    print(
        json.dumps(
            model.model_dump(mode="json", exclude_none=True),
            ensure_ascii=False,
            indent=2,
        )
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        with ShopMindReferenceClient(
            base_url=args.base_url,
            timeout_seconds=args.timeout_seconds,
        ) as client:
            if args.command == "chat":
                _print_model(
                    client.chat(
                        message=args.message,
                        user_id=args.user_id,
                        thread_id=args.thread_id,
                        include_debug=not args.no_debug,
                        idempotency_key=args.idempotency_key,
                    )
                )
            elif args.command == "stream":
                for event in client.stream_chat(
                    message=args.message,
                    user_id=args.user_id,
                    thread_id=args.thread_id,
                    include_debug=not args.no_debug,
                    idempotency_key=args.idempotency_key,
                ):
                    _print_model(event)
            elif args.command == "confirm":
                _print_model(
                    client.confirm(
                        user_id=args.user_id,
                        pending_action_id=args.pending_action_id,
                        confirmed=args.approve,
                        thread_id=args.thread_id,
                        updated_arguments=_json_object(
                            args.updated_arguments_json
                        ),
                        include_debug=not args.no_debug,
                        idempotency_key=args.idempotency_key,
                    )
                )
            elif args.command == "memory":
                _print_model(
                    client.inspect_memory(
                        user_id=args.user_id,
                        memory_limit=args.limit,
                    )
                )
            else:
                _print_model(
                    client.inspect_run(
                        user_id=args.user_id,
                        run_id=args.run_id,
                        trace_id=args.trace_id,
                        event_limit=args.event_limit,
                    )
                )
        return 0
    except (
        ReferenceClientError,
        ValidationError,
        ValueError,
    ) as exc:
        code = (
            exc.code
            if isinstance(exc, ReferenceClientError)
            else "arguments_invalid"
        )
        print(f"ShopMind reference client: {code}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
