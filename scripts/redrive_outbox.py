"""Explicitly redrive one dead-lettered ShopMind Outbox event."""

from __future__ import annotations

import argparse
from uuid import UUID

from app.db.session import SessionLocal
from app.outbox.repository import redrive_event


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("event_id", type=UUID)
    args = parser.parse_args()
    session = SessionLocal()
    try:
        changed = redrive_event(session, event_id=args.event_id)
        if not changed:
            session.rollback()
            raise SystemExit("Only an existing dead-lettered event can be redriven.")
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
