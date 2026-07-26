from app.runtime import AgentEvent, EventVisibility
from app.runtime import LocalRuntimeCoordinationBackend
from app.runtime.streaming import (
    LocalStreamConcurrencyLimiter,
    StreamAdmissionController,
    encode_sse_event,
)


def test_encode_sse_event_preserves_sequence_and_json_payload():
    frame = encode_sse_event(
        AgentEvent(
            sequence=4,
            event_type="context.built",
            visibility=EventVisibility.INTERNAL,
            payload={"estimated_tokens": 12},
        )
    )

    assert frame.startswith("event: context.built\nid: 4\ndata: ")
    assert '"estimated_tokens": 12' in frame
    assert frame.endswith("\n\n")


def test_local_stream_concurrency_limiter_rejects_excess_and_recovers_capacity():
    limiter = LocalStreamConcurrencyLimiter()

    assert limiter.try_acquire(1) is True
    assert limiter.active_count == 1
    assert limiter.try_acquire(1) is False

    limiter.release()
    assert limiter.active_count == 0
    assert limiter.try_acquire(1) is True
    limiter.release()


def test_stream_admission_controller_uses_token_specific_leases():
    controller = StreamAdmissionController(LocalRuntimeCoordinationBackend())

    first = controller.try_acquire(2, lease_ttl_ms=30_000)
    second = controller.try_acquire(2, lease_ttl_ms=30_000)
    rejected = controller.try_acquire(2, lease_ttl_ms=30_000)

    assert first.accepted is True
    assert second.accepted is True
    assert rejected.accepted is False
    assert first.lease_id != second.lease_id
    assert controller.renew(first.lease_id, lease_ttl_ms=30_000).renewed is True
    assert controller.release(first.lease_id).released is True
    assert controller.release(first.lease_id).released is False
    assert controller.try_acquire(2, lease_ttl_ms=30_000).accepted is True
