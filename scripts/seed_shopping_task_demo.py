"""Seed only the bounded catalog/task facts needed by the private demo schema."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.catalog.models import CatalogCategory, CatalogProduct, CatalogSku
from app.core.settings import get_settings
from app.shopping_tasks.models import CatalogCompatibilityRule, ShoppingPolicyRule
from scripts.seed_shopmind_catalog import load_catalog_seed, seed_catalog


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema", required=True)
    args = parser.parse_args()
    engine = create_engine(get_settings().database_url, pool_pre_ping=True)
    fixtures = json.loads((ROOT / "data" / "shopping_task_fixtures.json").read_text(encoding="utf-8"))
    try:
        with engine.connect() as connection:
            connection.execute(text(f'SET search_path TO "{args.schema}", public'))
            connection.commit()
            Session = sessionmaker(bind=connection)
            session = Session()
            try:
                for code in ("laptop", "monitor"):
                    seed_catalog(session, load_catalog_seed(ROOT / "data" / "catalog" / f"{code}_catalog.json"))
                seed_catalog(session, load_catalog_seed(ROOT / "data" / "shopping_task_dock_catalog.json"))
                for item in fixtures["compatibility_rules"]:
                    if session.scalar(select(CatalogCompatibilityRule).where(CatalogCompatibilityRule.left_sku_code == item["left_sku"], CatalogCompatibilityRule.right_sku_code == item["right_sku"], CatalogCompatibilityRule.rule_version == "compatibility.v1")) is None:
                        session.add(CatalogCompatibilityRule(left_sku_code=item["left_sku"], right_sku_code=item["right_sku"], state=item["state"], reason=item["reason"], rule_version="compatibility.v1", source_ref_json={"source": "catalog", "source_id": item["source_id"], "source_version": "2026.09.20", "verified": True}))
                thunder = "DOCK-THUNDER-12-100"
                monitor_skus = session.scalars(select(CatalogSku).join(CatalogProduct, CatalogSku.product_id == CatalogProduct.id).join(CatalogCategory, CatalogProduct.category_id == CatalogCategory.id).where(CatalogCategory.code == "monitor")).all()
                for monitor in monitor_skus:
                    if session.scalar(select(CatalogCompatibilityRule).where(CatalogCompatibilityRule.left_sku_code == monitor.sku_code, CatalogCompatibilityRule.right_sku_code == thunder, CatalogCompatibilityRule.rule_version == "compatibility.v1")) is None:
                        session.add(CatalogCompatibilityRule(left_sku_code=monitor.sku_code, right_sku_code=thunder, state="supported", reason="Controlled demo fact: documented display output and power path.", rule_version="compatibility.v1", source_ref_json={"source": "catalog", "source_id": f"compat-demo-{monitor.sku_code}", "source_version": "2026.09.20", "verified": True}))
                policy = fixtures["policy_rules"][0]
                if session.scalar(select(ShoppingPolicyRule).where(ShoppingPolicyRule.policy_type == policy["policy_type"], ShoppingPolicyRule.region == policy["region"], ShoppingPolicyRule.channel == policy["channel"], ShoppingPolicyRule.active.is_(True))) is None:
                    session.add(ShoppingPolicyRule(policy_type=policy["policy_type"], region=policy["region"], channel=policy["channel"], valid_from=datetime.now(timezone.utc), return_window_days=policy["return_window_days"], requires_unopened=policy["requires_unopened"], source_ref_json={"source": "policy", "source_id": policy["source_id"], "source_version": policy["source_version"], "verified": True}))
                session.commit()
            finally:
                session.close()
    finally:
        engine.dispose()
    print(f"seeded private task schema: {args.schema}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
