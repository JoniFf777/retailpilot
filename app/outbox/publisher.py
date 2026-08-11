"""Delivery orchestration for claimed Outbox events."""

from __future__ import annotations

import logging
from collections.abc import Callable

from sqlalchemy.orm import Session

from app.core.logging import log_event
from app.core.settings import Settings
from app.integrations.rocketmq import RocketMQPublisher
from app.outbox.repository import (
    OutboxClaim,
    claim_pending,
    mark_failure,
    mark_published,
    reclaim_expired,
)


logger = logging.getLogger(__name__)


class OutboxPublisher:
    """Claims in short DB transactions and publishes outside them."""

    def __init__(
        self,
        session_factory: Callable[[], Session],
        settings: Settings,
        *,
        publisher: RocketMQPublisher | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._publisher = publisher

    def _publisher_or_create(self) -> RocketMQPublisher:
        if self._publisher is None:
            self._publisher = RocketMQPublisher(self._settings)
        return self._publisher

    def startup(self) -> None:
        self._publisher_or_create().startup()

    def shutdown(self) -> None:
        if self._publisher is not None:
            self._publisher.shutdown()

    def run_once(self) -> int:
        session = self._session_factory()
        try:
            reclaim_expired(
                session,
                max_attempts=self._settings.shopmind_outbox_max_attempts,
            )
            session.commit()
        except Exception:
            session.rollback()
            session.close()
            raise
        finally:
            if session.is_active:
                session.close()

        session = self._session_factory()
        try:
            claims = claim_pending(
                session,
                batch_size=self._settings.shopmind_outbox_batch_size,
                lease_seconds=self._settings.shopmind_outbox_lease_seconds,
            )
            session.commit()
        except Exception:
            session.rollback()
            session.close()
            raise
        finally:
            if session.is_active:
                session.close()

        for claim in claims:
            log_event(
                "outbox.claimed",
                outbox_event_id=claim.event_id,
                aggregate_id=claim.envelope.aggregate_id,
                aggregate_sequence=claim.envelope.aggregate_sequence,
                attempt_count=claim.attempt_count,
                status="publishing",
            )
            self._publish_claim(claim)
        return len(claims)

    def _publish_claim(self, claim: OutboxClaim) -> None:
        try:
            broker_message_id = self._publisher_or_create().publish(claim.envelope)
        except Exception as exc:
            safe_failure = f"RocketMQ publish failed ({type(exc).__name__})"
            session = self._session_factory()
            try:
                mark_failure(
                    session,
                    event_id=claim.event_id,
                    lease_owner=claim.lease_owner,
                    attempt_count=claim.attempt_count,
                    error=safe_failure,
                    max_attempts=self._settings.shopmind_outbox_max_attempts,
                    base_backoff_seconds=self._settings.shopmind_outbox_base_backoff_seconds,
                    max_backoff_seconds=self._settings.shopmind_outbox_max_backoff_seconds,
                )
                session.commit()
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()
            log_event(
                "outbox.publish.failed",
                outbox_event_id=claim.event_id,
                aggregate_id=claim.envelope.aggregate_id,
                aggregate_sequence=claim.envelope.aggregate_sequence,
                attempt_count=claim.attempt_count,
                status=(
                    "dead_letter"
                    if claim.attempt_count >= self._settings.shopmind_outbox_max_attempts
                    else "pending"
                ),
                error_code="publish_failed",
                error_class=type(exc).__name__,
                error_message=safe_failure,
            )
            if claim.attempt_count >= self._settings.shopmind_outbox_max_attempts:
                log_event(
                    "outbox.dead_lettered",
                    outbox_event_id=claim.event_id,
                    aggregate_id=claim.envelope.aggregate_id,
                    aggregate_sequence=claim.envelope.aggregate_sequence,
                    attempt_count=claim.attempt_count,
                    status="dead_letter",
                )
            return

        session = self._session_factory()
        try:
            updated = mark_published(
                session,
                event_id=claim.event_id,
                lease_owner=claim.lease_owner,
                broker_message_id=broker_message_id,
            )
            session.commit()
            if not updated:
                logger.info("Ignoring stale Outbox publish completion for %s", claim.event_id)
            else:
                log_event(
                    "outbox.publish.succeeded",
                    outbox_event_id=claim.event_id,
                    aggregate_id=claim.envelope.aggregate_id,
                    aggregate_sequence=claim.envelope.aggregate_sequence,
                    attempt_count=claim.attempt_count,
                    status="published",
                )
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def run_forever(self, stop_event) -> None:
        self.startup()
        try:
            while not stop_event.is_set():
                processed = self.run_once()
                if processed == 0:
                    stop_event.wait(self._settings.shopmind_outbox_poll_interval_seconds)
        finally:
            self.shutdown()


__all__ = ["OutboxPublisher"]
