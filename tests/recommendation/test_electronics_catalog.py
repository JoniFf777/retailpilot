import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4, uuid5

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from agents.shopmind_multi_agent.graph import invoke_shopmind_multi_agent
from app.catalog.models import CatalogCategory, CatalogInventory, CatalogProduct, CatalogSku
from app.db.base import Base
from app.db.models import AgentRun, ConversationThread
from app.recommendation.categories import default_category_registry
from app.recommendation.providers import FakeCatalogCandidateProvider, FakeRecommendationPreferenceProvider
from app.recommendation.rag import FakeRecommendationEvidenceProvider
from app.recommendation.request import parse_recommendation_request
from app.recommendation.service import build_recommendation
from app.schemas.catalog import CatalogAttributeDefinition, CatalogSkuCandidate
from app.schemas.recommendation import CategoryAttributeConstraint, RecommendationRequest
from app.services.pending_actions import confirm_add_to_cart, create_add_to_cart_pending_action


ROOT = Path(__file__).resolve().parents[2]
NAMESPACE = UUID("5f9c2e5c-6f1b-4e8c-9d5d-3b0c14d1d90e")
NEW_CATEGORIES = ("phone", "tablet", "keyboard", "mouse", "headphones", "speaker", "camera", "router")
ALL_CATEGORIES = ("laptop", "monitor", *NEW_CATEGORIES)


def managed_candidates(category: str) -> list[CatalogSkuCandidate]:
    seed = json.loads((ROOT / "data" / "catalog" / f"{category}_catalog.json").read_text(encoding="utf-8"))
    definitions = [CatalogAttributeDefinition.model_validate(item) for item in seed["attribute_definitions"]]
    return [
        CatalogSkuCandidate(
            product_id=uuid5(NAMESPACE, row["product_code"]),
            product_code=row["product_code"],
            legacy_product_id=row["legacy_product_id"],
            product_name=row["name"],
            brand=row["brand"],
            sku_id=uuid5(NAMESPACE, row["sku"]["sku_code"]),
            sku_code=row["sku"]["sku_code"],
            sku_name=row["sku"]["name"],
            money_amount=Decimal(row["sku"]["money_amount"]),
            currency=row["sku"]["currency"],
            product_attributes=row["attributes"],
            variant_attributes=row["sku"].get("variant_attributes", {}),
            attribute_definitions=definitions,
            available_quantity=row["sku"]["inventory"],
        )
        for row in seed["products"]
    ]


def request_for_category(category: str, candidates: list[CatalogSkuCandidate]) -> RecommendationRequest:
    definition = default_category_registry().schema_for(category)
    candidate = next(item for item in candidates if item.available_quantity > 0)
    attributes: dict[str, CategoryAttributeConstraint] = {}
    for attribute in definition.attributes:
        if not attribute.required:
            continue
        value = candidate.attributes[attribute.canonical_catalog_key]
        attributes[attribute.key] = CategoryAttributeConstraint(value=value, operator="eq", role="hard")
    soft = next(
        (
            attribute
            for attribute in definition.attributes
            if attribute.role == "soft" and candidate.attributes.get(attribute.canonical_catalog_key) is not None
        ),
        None,
    )
    if soft is not None:
        value = candidate.attributes[soft.canonical_catalog_key]
        attributes[soft.key] = CategoryAttributeConstraint(
            value=value,
            operator="enum_match" if soft.type == "enum" else "eq",
            role="soft",
        )
    return RecommendationRequest(
        category=category,
        budget_max=candidate.money_amount + Decimal("1000"),
        budget_currency="CNY",
        category_attributes=attributes,
    )


def test_registry_resolves_all_ten_categories_and_aliases() -> None:
    registry = default_category_registry()
    assert {definition.code for definition in registry.supported_categories()} == set(ALL_CATEGORIES)
    for category in ALL_CATEGORIES:
        assert registry.resolve_code_or_alias(category) == category
    assert registry.resolve_code_or_alias("手机") == "phone"
    assert registry.resolve_code_or_alias("无线路由器") == "router"


def test_each_new_category_has_generic_recommendation_coverage() -> None:
    for category in NEW_CATEGORIES:
        candidates = managed_candidates(category)
        request = request_for_category(category, candidates)
        result = build_recommendation(candidates, request)
        repeat = build_recommendation(list(reversed(candidates)), request)
        assert result.outcome == "recommended", category
        assert result.recommendations, category
        assert result.recommendations[0].comparison_fields, category
        assert [item.sku_id for item in result.recommendations] == [item.sku_id for item in repeat.recommendations], category
        assert build_recommendation(candidates, request.model_copy(update={"budget_max": Decimal("1")})).outcome == "no_match", category
        assert any(item.available_quantity == 0 for item in candidates), category


def test_new_categories_keep_cross_category_isolation_and_missing_soft_fields() -> None:
    registry = default_category_registry()
    phone = managed_candidates("phone")
    request = request_for_category("phone", phone)
    invalid = request.model_copy(update={"category_attributes": {"router_speed": {"value": 1000, "operator": "gte", "role": "soft"}}})
    assert build_recommendation(phone, invalid).error_code == "invalid_category_attribute"
    missing_soft = next(item for item in phone if "connectivity" not in item.product_attributes or "camera_mp" not in item.product_attributes)
    result = build_recommendation([missing_soft], request)
    assert result.outcome in {"recommended", "no_match"}
    assert registry.resolve_code_or_alias("printer") is None


def test_phone_keyboard_router_use_the_same_agent_path() -> None:
    for category in ("phone", "keyboard", "router"):
        result = invoke_shopmind_multi_agent(
            f"recommend {category}",
            catalog_candidate_provider=FakeCatalogCandidateProvider(managed_candidates(category)),
            recommendation_preference_provider=FakeRecommendationPreferenceProvider(),
            recommendation_evidence_provider=FakeRecommendationEvidenceProvider(),
        )
        assert result["recommendation"]["category"] == category
        assert result["recommendation"]["recommendations"]
        assert result["recommendation"]["recommendations"][0]["comparison_fields"]


def test_phone_and_router_keep_pending_action_expected_version_and_cart_boundary() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        for index, category_code in enumerate(("phone", "router")):
            candidate = next(item for item in managed_candidates(category_code) if item.available_quantity > 0)
            category = CatalogCategory(id=uuid4(), code=category_code, name=category_code, status="active")
            product = CatalogProduct(
                id=candidate.product_id,
                product_code=candidate.product_code,
                legacy_product_id=candidate.legacy_product_id,
                category=category,
                brand=candidate.brand,
                name=candidate.product_name,
                sale_status="active",
                attributes_json=candidate.product_attributes,
            )
            sku = CatalogSku(
                id=candidate.sku_id,
                product=product,
                sku_code=candidate.sku_code,
                name=candidate.sku_name,
                money_amount=candidate.money_amount,
                currency=candidate.currency,
                sale_status="active",
                variant_attributes_json=candidate.variant_attributes,
            )
            inventory = CatalogInventory(sku=sku, on_hand_quantity=3, reserved_quantity=0, version=0)
            thread = ConversationThread(
                id=f"electronics-thread-{index}", user_id=f"electronics-user-{index}", client_thread_id=f"electronics-thread-{index}", status="active", metadata_json={}, created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc)
            )
            result = build_recommendation([candidate], request_for_category(category_code, [candidate]))
            run = AgentRun(
                id=f"electronics-run-{index}", thread=thread, user_id=f"electronics-user-{index}", operation="chat", mode="multi", status="completed", request_id=f"electronics-request-{index}", trace_id=f"electronics-trace-{index}", request_json={}, result_json={"recommendation": result.model_dump(mode="json")}, usage_json={}, tool_call_records_json=[], metadata_json={}, started_at=datetime.now(timezone.utc)
            )
            session.add_all([category, product, sku, inventory, thread, run])
            session.flush()
            view = create_add_to_cart_pending_action(session, user_id=f"electronics-user-{index}", thread_id=f"electronics-thread-{index}", source_run_id=f"electronics-run-{index}", sku_id=candidate.sku_id, quantity=1)
            confirmed = confirm_add_to_cart(session, pending_action_id=view.pending_action_id, user_id=f"electronics-user-{index}", thread_id=f"electronics-thread-{index}", expected_version=view.version)
            assert confirmed.cart_item is not None
            assert confirmed.cart_item.sku_id == candidate.sku_id
            session.rollback()
    finally:
        session.close()
