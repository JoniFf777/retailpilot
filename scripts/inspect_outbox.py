"""Print a bounded, payload-free ShopMind Outbox operational summary."""

from __future__ import annotations

import argparse
import json

from app.db.session import SessionLocal
from app.outbox.repository import get_outbox_operational_snapshot


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum recent dead-letter/failure rows to include (1-10).",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    args = parser.parse_args()
    session = SessionLocal()
    try:
        report = get_outbox_operational_snapshot(
            session,
            recent_limit=max(1, min(args.limit, 10)),
        )
    except Exception as exc:
        session.rollback()
        if args.json:
            print(
                json.dumps(
                    {
                        "status": "error",
                        "error_code": "outbox_inspection_failed",
                        "error_class": type(exc).__name__,
                        "error_message": "Outbox inspection failed.",
                    }
                )
            )
        else:
            print("Outbox inspection failed.")
        return 1
    finally:
        session.close()

    report = {"status": "ok", **report}
    if args.json:
        print(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
