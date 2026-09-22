import json
from pathlib import Path

from app.shopping_tasks.category_registry import default_task_category_registry


def test_dock_schema_and_isolated_fixture_are_bounded() -> None:
    registry = default_task_category_registry()
    dock = registry.schema_for("dock")
    assert {field.key for field in dock.attributes} == {"video_outputs", "power_delivery_w", "host_interface"}
    payload = json.loads((Path(__file__).resolve().parents[2] / "app" / "shopping_tasks" / "dock_category.json").read_text(encoding="utf-8"))
    catalog = json.loads((Path(__file__).resolve().parents[2] / "data" / "shopping_task_dock_catalog.json").read_text(encoding="utf-8"))
    assert len(catalog["products"]) == 4
    assert any(row["sku"]["inventory"] == 0 for row in catalog["products"])
    assert any("video_outputs" not in row["attributes"] for row in catalog["products"])
    task_fixtures = json.loads((Path(__file__).resolve().parents[2] / "data" / "shopping_task_fixtures.json").read_text(encoding="utf-8"))
    assert len(task_fixtures["compatibility_rules"]) == 4
    assert len(task_fixtures["diagnostic_checks"]) == 2
    assert task_fixtures["policy_rules"][0]["source_version"]
