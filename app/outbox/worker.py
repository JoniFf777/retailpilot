"""Standalone worker facade for the transactional Outbox publisher."""

from app.outbox.publisher import OutboxPublisher

__all__ = ["OutboxPublisher"]
