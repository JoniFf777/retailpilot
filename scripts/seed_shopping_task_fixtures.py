"""Seed controlled compatibility and policy facts without clearing the DB."""

from __future__ import annotations

from datetime import datetime, timezone
import argparse
import json
from pathlib import Path

from sqlalchemy import select

from app.db.session import SessionLocal
from app.shopping_tasks.models import CatalogCompatibilityRule, ShoppingPolicyRule


FIXTURE_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "shopping_task_fixtures.json"
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    session = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        fixtures = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        for item in fixtures["compatibility_rules"]:
            left, right, state, reason = (
                item["left_sku"],
                item["right_sku"],
                item["state"],
                item["reason"],
            )
            if (
                session.scalar(
                    select(CatalogCompatibilityRule).where(
                        CatalogCompatibilityRule.left_sku_code == left,
                        CatalogCompatibilityRule.right_sku_code == right,
                        CatalogCompatibilityRule.rule_version == "compatibility.v1",
                    )
                )
                is None
            ):
                session.add(
                    CatalogCompatibilityRule(
                        left_sku_code=left,
                        right_sku_code=right,
                        state=state,
                        reason=reason,
                        rule_version="compatibility.v1",
                        source_ref_json={
                            "source": "catalog",
                            "source_id": item["source_id"],
                            "source_version": "2026.09.20",
                            "verified": True,
                        },
                    )
                )
        if (
            session.scalar(
                select(ShoppingPolicyRule).where(
                    ShoppingPolicyRule.policy_type == "return",
                    ShoppingPolicyRule.region == "CN",
                    ShoppingPolicyRule.channel == "online",
                    ShoppingPolicyRule.active.is_(True),
                )
            )
            is None
        ):
            policy = fixtures["policy_rules"][0]
            session.add(
                ShoppingPolicyRule(
                    policy_type=policy["policy_type"],
                    region=policy["region"],
                    channel=policy["channel"],
                    valid_from=now.replace(hour=0, minute=0, second=0, microsecond=0),
                    return_window_days=policy["return_window_days"],
                    requires_unopened=policy["requires_unopened"],
                    source_ref_json={
                        "source": "policy",
                        "source_id": policy["source_id"],
                        "source_version": policy["source_version"],
                        "verified": True,
                    },
                )
            )
        if args.execute:
            session.commit()
            print("shopping task fixtures committed")
        else:
            session.rollback()
            print("plan only; pass --execute against an isolated database")
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
