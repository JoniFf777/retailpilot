"""Run the standalone ShopMind transactional Outbox publisher."""

from __future__ import annotations

import logging
import signal
import threading

from app.core.settings import get_settings
from app.db.session import SessionLocal
from app.outbox.publisher import OutboxPublisher


def main() -> int:
    settings = get_settings()
    if not settings.shopmind_outbox_enabled:
        raise SystemExit(
            "Outbox publisher is disabled. Set SHOPMIND_OUTBOX_ENABLED=true for the worker."
        )
    logging.basicConfig(level=logging.INFO)
    stop_event = threading.Event()
    for signal_name in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signal_name, lambda *_args: stop_event.set())
    worker = OutboxPublisher(SessionLocal, settings)
    worker.run_forever(stop_event)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
