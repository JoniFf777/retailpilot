from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.recommendation.evidence import sanitize_evidence
from app.recommendation.constraints import parse_laptop_constraints
from app.recommendation.service import build_laptop_recommendation
from app.schemas.catalog import CatalogSkuCandidate
from app.schemas.recommendation import LaptopConstraints, Money, ProductSpecificationView


def candidate(product_id, sku_code: str, *, price="5000", memory=16, stock=2, cpu="i7"):
    return CatalogSkuCandidate(product_id=product_id, product_code=f"P-{sku_code}", product_name=sku_code, brand="Test",
        sku_id=uuid4(), sku_code=sku_code, sku_name=sku_code, money_amount=Decimal(price), currency="CNY",
        product_attributes={"memory_gb": memory, "storage_gb": 512, "weight_kg": 1.2, "screen_inches": 14, "cpu_tier": cpu, "gpu_tier": "entry", "use_cases": ["office"]}, available_quantity=stock)


def test_money_and_specification_public_types_are_strings_when_decimal() -> None:
    assert Money(amount="12", currency="人民币").model_dump() == {"amount": "12.00", "currency": "CNY"}
    spec = ProductSpecificationView(code="weight", name="Weight", value_type="decimal", value="1.20")
    assert spec.value == "1.20"
    assert Money.model_json_schema()["properties"]["amount"]["type"] == "string"


def test_money_rejects_negative_nonfinite_and_excess_precision() -> None:
    for amount in ("-0.01", "NaN", "Infinity", "1.001"):
        with pytest.raises(ValidationError):
            Money(amount=amount, currency="CNY")
    assert Money(amount="5999", currency=chr(0xFFE5)).model_dump() == {"amount": "5999.00", "currency": "CNY"}
    assert Money(amount="10.00", currency="JPY").currency == "JPY"


def test_product_specification_is_strict_about_bool_integer_and_decimal() -> None:
    with pytest.raises(ValidationError):
        ProductSpecificationView(code="memory", name="Memory", value_type="integer", value=True)
    with pytest.raises(ValidationError):
        ProductSpecificationView(code="touch", name="Touch", value_type="boolean", value=1)
    with pytest.raises(ValidationError):
        ProductSpecificationView(code="weight", name="Weight", value_type="decimal", value=1.2)
    with pytest.raises(ValidationError):
        ProductSpecificationView(code="items", name="Items", value_type="string_list", value=["ok", 1])


def test_deterministic_chinese_constraint_parser_normalizes_currency_and_usage() -> None:
    parsed = parse_laptop_constraints("预算 6000 元以内，主要用于 Java 开发，偶尔剪视频，内存至少 16GB，希望尽量轻。")
    assert parsed.budget_max == Decimal("6000")
    assert parsed.budget_currency == "CNY"
    assert parsed.memory_min_gb == 16
    assert parsed.primary_use_cases == ["java_development"]
    assert parsed.secondary_use_cases == ["video_editing"]
    assert parse_laptop_constraints("预算 JPY 6000，内存至少 16GB").budget_currency == "JPY"


def test_ranking_filters_hard_constraints_deduplicates_spu_and_keeps_alternative_skus() -> None:
    first = uuid4(); second = uuid4()
    result = build_laptop_recommendation([candidate(first, "A-EXPENSIVE", price="6000"), candidate(first, "A-CHEAP", price="5000"), candidate(second, "B", price="5500")], LaptopConstraints(budget_max=Decimal("7000"), budget_currency="元", memory_min_gb=16))
    assert result.outcome == "recommended"
    assert len(result.recommendations) == 2
    assert result.recommendations[0].sku_name == "A-CHEAP"
    assert result.recommendations[0].alternative_skus[0].sku_name == "A-EXPENSIVE"


def test_no_match_clarification_and_stable_tie_break() -> None:
    a, b = uuid4(), uuid4()
    no_match = build_laptop_recommendation([candidate(a, "A", memory=8)], LaptopConstraints(memory_min_gb=16))
    assert no_match.outcome == "no_match"
    clarification = build_laptop_recommendation([candidate(a, "A")], LaptopConstraints(budget_max=Decimal("100"), budget_currency="USD"))
    assert clarification.outcome == "clarification_required"
    tie = build_laptop_recommendation([candidate(a, "Z", price="5000"), candidate(b, "A", price="5000")], LaptopConstraints())
    assert [item.sku_name for item in tie.recommendations] == ["A", "Z"]


def test_evidence_sanitizer_whitelists_public_fields() -> None:
    evidence = sanitize_evidence([{"source": "catalog", "type": "product", "field": "brand", "value": "Test", "ref": "x", "raw_payload": "secret"}])
    assert evidence[0].model_dump() == {"source": "catalog", "type": "product", "field": "brand", "value": "Test", "ref": "x"}
