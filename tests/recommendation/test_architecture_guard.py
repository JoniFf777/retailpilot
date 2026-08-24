from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_generic_paths_have_no_fixture_or_category_dispatch_literals() -> None:
    paths = [
        ROOT / "app/recommendation/request.py",
        ROOT / "app/recommendation/constraints.py",
        ROOT / "app/recommendation/ranking.py",
        ROOT / "app/recommendation/gate.py",
        ROOT / "agents/shopmind_multi_agent/recommendation_nodes.py",
        ROOT / "scripts/validate_shopmind_catalog.py",
        ROOT / "frontend/src/features/recommendation/RecommendationPanel.tsx",
        ROOT / "frontend/src/features/recommendation/RecommendationCard.tsx",
        ROOT / "frontend/src/features/recommendation/StructuredConstraintsPanel.tsx",
    ]
    source = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    assert "test_accessory" not in source
    assert "battery_wh" not in source
    assert "structured_laptop_recommendation" not in source
    assert "structured_monitor_recommendation" not in source
    assert 'or "laptop"' not in source
    assert "REQUIRED_ATTRIBUTES" not in source


def test_generic_renderer_has_no_category_render_branch() -> None:
    paths = Path(ROOT / "frontend/src/features/recommendation").glob("*.tsx")
    source = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    assert "category ===" not in source
    assert "category ?? \"laptop\"" not in source
