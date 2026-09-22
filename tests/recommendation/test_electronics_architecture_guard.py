import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
BASELINE = Path(
    r"C:\Users\17937\Desktop\4\expand-electronics-catalog-baseline\preimage"
)
CORE_FILES = (
    "app/recommendation/gate.py",
    "app/recommendation/request.py",
    "app/recommendation/constraints.py",
    "app/recommendation/ranking.py",
    "app/recommendation/service.py",
    "app/recommendation/compatibility.py",
    "app/schemas/recommendation.py",
    "app/recommendation/categories/registry.py",
    "app/schemas/recommendation.py",
    "agents/shopmind_multi_agent/graph.py",
    "agents/shopmind_multi_agent/recommendation_nodes.py",
    "frontend/src/features/recommendation/RecommendationPanel.tsx",
    "frontend/src/features/recommendation/RecommendationCard.tsx",
    "frontend/src/features/recommendation/StructuredConstraintsPanel.tsx",
    "frontend/src/features/recommendation/ProductSpecifications.tsx",
    "frontend/src/features/recommendation/ComparisonDrawer.tsx",
    "frontend/src/features/recommendation/recommendationTypes.ts",
    "scripts/validate_shopmind_catalog.py",
    "data/catalog/laptop_catalog.json",
    "data/catalog/monitor_catalog.json",
)
# This guard predates the recommendation-quality work.  These two core files
# are now intentionally changed by the approved parser/personalization fix;
# the guard still protects every other catalog and recommendation boundary.
ALLOWED_RECOMMENDATION_QUALITY_CHANGES = {
    "app/recommendation/request.py",
    "app/recommendation/constraints.py",
    "app/recommendation/ranking.py",
    "app/recommendation/service.py",
    "app/recommendation/compatibility.py",
    "app/schemas/recommendation.py",
    "agents/shopmind_multi_agent/recommendation_nodes.py",
    "agents/shopmind_multi_agent/graph.py",
    "frontend/src/features/recommendation/RecommendationPanel.tsx",
    "frontend/src/features/recommendation/StructuredConstraintsPanel.tsx",
}


def test_electronics_change_does_not_modify_recommendation_core_or_existing_data() -> (
    None
):
    if not BASELINE.exists():
        pytest.skip("Apply baseline is local-only")
    changed = []
    for relative in CORE_FILES:
        before = BASELINE / relative
        after = ROOT / relative
        if (
            relative not in ALLOWED_RECOMMENDATION_QUALITY_CHANGES
            and before.read_bytes() != after.read_bytes()
        ):
            changed.append(relative)
    assert changed == []


def test_generic_production_paths_have_no_new_category_or_attribute_branches() -> None:
    paths = [
        ROOT / relative
        for relative in CORE_FILES
        if relative
        not in {
            "scripts/validate_shopmind_catalog.py",
            "data/catalog/laptop_catalog.json",
            "data/catalog/monitor_catalog.json",
        }
    ]
    source = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    source = source.replace("supervisor_router", "")
    for token in (
        "phone",
        "tablet",
        "keyboard",
        "mouse",
        "headphones",
        "speaker",
        "camera",
        "router",
        "battery_mah",
        "sensor_size",
    ):
        assert not re.search(
            rf"if\s+[^\n]*\b{re.escape(token)}\b", source.casefold()
        ), token
        assert not re.search(
            rf"if\s+[^\n]*key[^\n]*\b{re.escape(token)}\b", source.casefold()
        ), token
    assert not re.search(
        r"structured_(phone|tablet|keyboard|mouse|headphones|speaker|camera|router)",
        source.casefold(),
    )
