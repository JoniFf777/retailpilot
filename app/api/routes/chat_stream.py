"""SSE compatibility endpoint for ordered runtime events."""

from __future__ import annotations

import asyncio
from concurrent.futures import Future as ConcurrentFuture
from time import monotonic
from threading import Event, Lock
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from app.core.chat_errors import (
    log_public_exception,
    public_failure_result,
)
from app.core.logging import log_event
from app.core.settings import get_settings
from app.api.chat_response import build_chat_response
from app.dependencies import agent as agent_dependency
from app.dependencies.security import bind_request_user, get_identity_boundary
from app.runtime import AgentEvent, EventVisibility, RunResult
from app.runtime.streaming import STREAM_ADMISSION_CONTROLLER, encode_sse_event
from app.schemas.chat import ChatRequest
from app.security import AuditRequestOperation, IdentityBoundary


router = APIRouter()
_STREAM_END = object()


def _legacy_stream_result(
    result: RunResult | dict[str, Any],
    *,
    request: ChatRequest,
    effective_user_id: str | None,
    include_debug: bool,
) -> dict[str, Any]:
    return build_chat_response(
        result,
        user_id=effective_user_id,
        thread_id=request.thread_id,
        include_debug=include_debug,
    ).model_dump(mode="json", exclude_none=True)


@router.post("/chat/stream")
async def chat_stream(
    request: ChatRequest,
    http_request: Request,
    identity_boundary: IdentityBoundary = Depends(get_identity_boundary),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> StreamingResponse:
    identity = bind_request_user(
        identity_boundary,
        request.user_id,
        require_user=False,
        request_operation=AuditRequestOperation.CHAT_STREAM,
    )
    settings = get_settings()
    admission = STREAM_ADMISSION_CONTROLLER.try_acquire(
        settings.shopmind_stream_max_concurrency,
        lease_ttl_ms=settings.shopmind_stream_admission_lease_ttl_ms,
    )
    if not admission.accepted:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many active streaming runs.",
        )
    lease_id = admission.lease_id
    if lease_id is None:  # The typed backend contract should make this unreachable.
        raise RuntimeError("Accepted stream admission did not return a lease.")

    queue: asyncio.Queue[object] = asyncio.Queue(
        maxsize=settings.shopmind_stream_event_buffer_size
    )
    loop = asyncio.get_running_loop()
    delivery_detached = Event()
    runtime_cancellation = Event()
    pending_deliveries: set[ConcurrentFuture[None]] = set()
    delivery_lock = Lock()

    def enqueue_event(event: AgentEvent) -> None:
        if delivery_detached.is_set():
            return
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            # Stop delivery when a slow/disconnected client exhausts its local buffer.
            # This must not cancel the authoritative runtime execution.
            delivery_detached.set()

    async def deliver_event(event: AgentEvent) -> None:
        enqueue_event(event)

    def forget_delivery(delivery: ConcurrentFuture[None]) -> None:
        with delivery_lock:
            pending_deliveries.discard(delivery)

    def event_sink(event: AgentEvent) -> None:
        if delivery_detached.is_set():
            return
        try:
            delivery = asyncio.run_coroutine_threadsafe(deliver_event(event), loop)
            with delivery_lock:
                pending_deliveries.add(delivery)
            delivery.add_done_callback(forget_delivery)
        except RuntimeError:
            delivery_detached.set()

    async def flush_event_deliveries() -> None:
        while True:
            with delivery_lock:
                deliveries = list(pending_deliveries)
            if not deliveries:
                return
            await asyncio.gather(
                *(asyncio.wrap_future(delivery) for delivery in deliveries),
                return_exceptions=True,
            )

    async def run_agent() -> None:
        try:
            call_kwargs = {
                "event_sink": event_sink,
                "cancellation_check": runtime_cancellation.is_set,
            }
            if idempotency_key:
                call_kwargs["idempotency_key"] = idempotency_key
            result = await asyncio.to_thread(
                agent_dependency.call_shopmind_agent,
                request.message,
                identity.effective_user_id,
                request.thread_id,
                **call_kwargs,
            )
            await flush_event_deliveries()
            if not delivery_detached.is_set():
                try:
                    queue.put_nowait(result)
                except asyncio.QueueFull:
                    delivery_detached.set()
        except Exception as exc:
            log_public_exception(
                "chat.stream_execution_failed",
                exc,
                thread_id=request.thread_id,
            )
            await flush_event_deliveries()
            if not delivery_detached.is_set():
                try:
                    queue.put_nowait(public_failure_result(exc))
                except asyncio.QueueFull:
                    delivery_detached.set()
        finally:
            if not delivery_detached.is_set():
                try:
                    queue.put_nowait(_STREAM_END)
                except asyncio.QueueFull:
                    delivery_detached.set()

    def consume_detached_task(completed_task: asyncio.Task) -> None:
        try:
            completed_task.result()
        except Exception as exc:
            log_event(
                "chat.stream.detached_task_failed",
                status="failed",
                error_code="runtime.detached_task_failed",
                error_class=type(exc).__name__,
                error_message="Detached Chat execution failed after transport loss.",
            )

    task = asyncio.create_task(run_agent())

    async def generate():
        last_sequence = 0
        next_renewal_at = (
            monotonic()
            + settings.shopmind_stream_admission_renew_interval_ms / 1_000
        )
        try:
            while True:
                if monotonic() >= next_renewal_at:
                    renewal = STREAM_ADMISSION_CONTROLLER.renew(
                        lease_id,
                        lease_ttl_ms=settings.shopmind_stream_admission_lease_ttl_ms,
                    )
                    if not renewal.renewed:
                        runtime_cancellation.set()
                    next_renewal_at = (
                        monotonic()
                        + settings.shopmind_stream_admission_renew_interval_ms / 1_000
                    )
                if await http_request.is_disconnected():
                    delivery_detached.set()
                    break
                if delivery_detached.is_set():
                    break
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=0.1)
                except TimeoutError:
                    continue

                if item is _STREAM_END:
                    break
                if isinstance(item, AgentEvent):
                    if item.visibility != EventVisibility.CLIENT or item.event_type in {
                        "run.completed", "run.failed", "run.cancelled", "run.timed_out"
                    }:
                        continue
                    last_sequence = max(last_sequence, item.sequence)
                    yield encode_sse_event(item)
                    continue
                if isinstance(item, (RunResult, dict)):
                    trace_id = item.trace_id if isinstance(item, RunResult) else None
                    sequence = (
                        (item.events[-1].sequence + 1)
                        if isinstance(item, RunResult) and item.events
                        else last_sequence + 1
                    )
                    final_event = AgentEvent(
                        sequence=sequence,
                        event_type="run.result",
                        trace_id=trace_id,
                        visibility=EventVisibility.CLIENT,
                        payload=_legacy_stream_result(
                            item,
                            request=request,
                            effective_user_id=identity.effective_user_id,
                            include_debug=request.include_debug,
                        ),
                    )
                    yield encode_sse_event(final_event)
                    continue

                error_event = AgentEvent(
                    sequence=last_sequence + 1,
                    event_type="run.result",
                    visibility=EventVisibility.CLIENT,
                    payload=public_failure_result(
                        RuntimeError("unexpected stream result type")
                    ),
                )
                yield encode_sse_event(error_event)
        finally:
            if not task.done():
                delivery_detached.set()
                task.add_done_callback(consume_detached_task)
            else:
                consume_detached_task(task)
            STREAM_ADMISSION_CONTROLLER.release(lease_id)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
