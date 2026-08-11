"""Unit coverage for immutable Outbox contracts and worker-only RocketMQ loading."""

from __future__ import annotations

import sys
import types
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.core.settings import Settings
from app.integrations.rocketmq import RocketMQPublisher
from app.outbox.contracts import OutboxEventEnvelope
from app.outbox.repository import _backoff_seconds


def _envelope() -> OutboxEventEnvelope:
    return OutboxEventEnvelope(
        event_id=uuid4(),
        event_type="shopmind.order.created.v1",
        aggregate_id=uuid4(),
        aggregate_sequence=1,
        occurred_at=datetime.now(timezone.utc),
        payload={"order_id": "order-1", "items": []},
    )


def test_outbox_envelope_is_versioned_and_pii_safe() -> None:
    envelope = _envelope()
    dumped = envelope.model_dump(mode="json")

    assert envelope.event_version == 1
    assert envelope.aggregate_type == "order"
    assert dumped["event_id"] == str(envelope.event_id)
    assert "request_hash" not in dumped
    assert "provider_idempotency_key" not in dumped


def test_outbox_backoff_is_deterministic_and_capped() -> None:
    assert [_backoff_seconds(attempt) for attempt in range(1, 5)] == [5, 10, 20, 40]
    assert _backoff_seconds(12) == 900


def test_rocketmq_sdk_is_loaded_only_when_publisher_starts(monkeypatch) -> None:
    class FakeCredentials:
        def __init__(self, *_args):
            pass

    class FakeClientConfiguration:
        def __init__(self, endpoint, credentials):
            self.endpoint = endpoint
            self.credentials = credentials

    class FakeMessage:
        pass

    class FakeProducer:
        def __init__(self, _config, topics):
            self.topics = topics
            self.started = False

        def startup(self):
            self.started = True

        def send(self, message):
            assert message.message_group
            assert message.keys
            assert message.tag == "shopmind.order.created.v1"
            return SimpleNamespace(message_id="broker-message-1")

        def shutdown(self):
            self.started = False

    fake_module = types.ModuleType("rocketmq")
    fake_module.ClientConfiguration = FakeClientConfiguration
    fake_module.Credentials = FakeCredentials
    fake_module.Message = FakeMessage
    fake_module.Producer = FakeProducer
    monkeypatch.setitem(sys.modules, "rocketmq", fake_module)

    publisher = RocketMQPublisher(
        Settings(shopmind_outbox_rocketmq_endpoint="127.0.0.1:8081")
    )
    publisher.startup()
    assert publisher.publish(_envelope()) == "broker-message-1"
    publisher.shutdown()
