import json
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid5

from app.recommendation.request import parse_recommendation_request
from app.recommendation.service import build_recommendation
from app.schemas.catalog import CatalogAttributeDefinition, CatalogSkuCandidate


ROOT = Path(__file__).resolve().parents[2]
NAMESPACE = UUID("5f9c2e5c-6f1b-4e8c-9d5d-3b0c14d1d90e")


def managed_candidates(path: Path) -> list[CatalogSkuCandidate]:
    seed = json.loads(path.read_text(encoding="utf-8"))
    definitions = [CatalogAttributeDefinition.model_validate(item) for item in seed["attribute_definitions"]]
    result = []
    for row in seed["products"]:
        sku = row["sku"]
        result.append(
            CatalogSkuCandidate(
                product_id=uuid5(NAMESPACE, row["product_code"]),
                product_code=row["product_code"],
                legacy_product_id=row["legacy_product_id"],
                product_name=row["name"],
                brand=row["brand"],
                sku_id=uuid5(NAMESPACE, sku["sku_code"]),
                sku_code=sku["sku_code"],
                sku_name=sku["name"],
                money_amount=Decimal(sku["money_amount"]),
                currency=sku["currency"],
                product_attributes=row["attributes"],
                variant_attributes=sku.get("variant_attributes", {}),
                attribute_definitions=definitions,
                available_quantity=sku["inventory"],
            )
        )
    return result


def test_laptop_seed_covers_value_development_portable_gaming_and_no_match() -> None:
    candidates = managed_candidates(ROOT / "data/catalog/laptop_catalog.json")
    development = build_recommendation(
        candidates,
        parse_recommendation_request("预算 7000 元，推荐一台 Java 开发、轻薄便携的笔记本，内存至少 16GB", "laptop"),
    )
    gaming = build_recommendation(
        candidates,
        parse_recommendation_request("预算 10000 元，推荐一台游戏本，内存至少 16GB", "laptop"),
    )
    no_match = build_recommendation(
        candidates,
        parse_recommendation_request("预算 3000 元，推荐一台内存至少 16GB 的笔记本", "laptop"),
    )

    assert development.outcome == "recommended"
    assert gaming.outcome == "recommended"
    assert any("gaming" in item.attributes.get("use_cases", []) for item in candidates)
    assert no_match.outcome == "no_match"


def test_monitor_seed_covers_office_gaming_resolution_price_and_unavailable() -> None:
    candidates = managed_candidates(ROOT / "data/catalog/monitor_catalog.json")
    office = build_recommendation(
        candidates,
        parse_recommendation_request("预算 1500 元，推荐一台办公显示器", "monitor"),
    )
    gaming = build_recommendation(
        candidates,
        parse_recommendation_request("预算 3500 元，推荐一台 27 英寸 1440p 144Hz 显示器用于游戏", "monitor"),
    )
    strict_no_match = build_recommendation(
        candidates,
        parse_recommendation_request("预算 800 元，推荐一台 4K 显示器", "monitor"),
    )

    assert office.outcome == "recommended"
    assert gaming.outcome == "recommended"
    assert all(item.availability.in_stock for item in gaming.recommendations)
    assert strict_no_match.outcome == "no_match"
