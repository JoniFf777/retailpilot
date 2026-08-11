"""Lazy Apache RocketMQ publisher adapter for the Outbox worker."""

from __future__ import annotations

import json
from typing import Any

from app.core.settings import Settings
from app.outbox.contracts import OutboxEventEnvelope


class RocketMQPublisherError(RuntimeError):
    """Configuration, SDK, or publish failure outside the business transaction."""


class RocketMQPublisher:
    """Process-local producer used only by the standalone publisher worker."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._producer: Any | None = None

    def startup(self) -> None:
        if self._producer is not None:
            return
        endpoint = self._settings.shopmind_outbox_rocketmq_endpoint
        topic = self._settings.shopmind_outbox_rocketmq_topic
        if not endpoint or not topic:
            raise RocketMQPublisherError(
                "RocketMQ publisher requires SHOPMIND_OUTBOX_ROCKETMQ_ENDPOINT and topic."
            )
        try:
            from rocketmq import ClientConfiguration, Credentials, Producer
        except ImportError as exc:  # pragma: no cover - depends on worker env
            raise RocketMQPublisherError(
                "Apache rocketmq-python-client is not installed in the publisher environment."
            ) from exc
        access_key = self._settings.shopmind_outbox_rocketmq_access_key
        secret_key = self._settings.shopmind_outbox_rocketmq_secret_key
        if (access_key is None) != (secret_key is None):
            raise RocketMQPublisherError(
                "RocketMQ access and secret keys must be configured together."
            )
        credentials = (
            Credentials(access_key.get_secret_value(), secret_key.get_secret_value())
            if access_key is not None and secret_key is not None
            else Credentials()
        )
        try:
            producer = Producer(ClientConfiguration(endpoint, credentials), (topic,))
            producer.startup()
        except Exception as exc:
            raise RocketMQPublisherError("RocketMQ producer startup failed.") from exc
        self._producer = producer

    def publish(self, envelope: OutboxEventEnvelope) -> str:
        if self._producer is None:
            raise RocketMQPublisherError("RocketMQ producer is not started.")
        try:
            from rocketmq import Message

            message = Message()
            message.topic = self._settings.shopmind_outbox_rocketmq_topic
            message.tag = envelope.event_type
            message.message_group = str(envelope.aggregate_id)
            message.keys = str(envelope.event_id)
            message.body = json.dumps(
                envelope.model_dump(mode="json"),
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
            receipt = self._producer.send(message)
            message_id = getattr(receipt, "message_id", None)
            if not message_id:
                raise RocketMQPublisherError("RocketMQ returned no message id.")
            return str(message_id)
        except RocketMQPublisherError:
            raise
        except Exception as exc:
            raise RocketMQPublisherError("RocketMQ publish failed.") from exc

    def shutdown(self) -> None:
        producer, self._producer = self._producer, None
        if producer is not None:
            producer.shutdown()


__all__ = ["RocketMQPublisher", "RocketMQPublisherError"]
