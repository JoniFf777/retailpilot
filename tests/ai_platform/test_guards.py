import pytest

from app.ai_platform.guards import (
    ShoppingFactConflict,
    ensure_no_business_writer,
    non_authoritative_document_metadata,
)


def test_dynamic_document_fields_are_quarantined() -> None:
    metadata = non_authoritative_document_metadata(
        {"product_id": "TECH-LAP-001", "price": 5999, "inventory": 2}
    )
    assert "price" not in metadata
    assert "inventory" not in metadata
    assert metadata["authority"] == "evidence_only"
    assert metadata["non_authoritative_fields"] == ["inventory", "price"]


def test_extension_writer_is_rejected() -> None:
    with pytest.raises(ShoppingFactConflict):
        ensure_no_business_writer({"side_effect": "sensitive_write"})
