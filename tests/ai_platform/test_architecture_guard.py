from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_extension_registry_does_not_import_business_writers():
    source = (ROOT / "app/ai_platform/extensions.py").read_text(encoding="utf-8")
    assert "tools.cart" not in source
    assert "app.services.orders" not in source
    assert "app.services.payments" not in source
