from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.catalog.models import CatalogCategory, CatalogInventory, CatalogProduct, CatalogSku
from app.db.base import Base
from app.db.models import AgentRun, ConversationThread, PendingAction
from app.repositories.shopmind_cart import list_cart_items
from app.schemas.recommendation import (
    AvailabilityView,
    LaptopConstraints,
    Money,
    Recommendation,
    RecommendationResult,
)
from app.services.pending_actions import (
    PendingActionServiceError,
    confirm_add_to_cart,
    create_add_to_cart_pending_action,
    pending_action_to_view,
)


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def seed_recommendation(session):
    category = CatalogCategory(id=uuid4(), code="laptop", name="Laptop", status="active")
    product = CatalogProduct(
        id=uuid4(), product_code="LP-001", legacy_product_id="TECH-LAP-001",
        category=category, brand="ShopMind", name="Demo Laptop", sale_status="active",
        attributes_json={},
    )
    sku = CatalogSku(
        id=uuid4(), product=product, sku_code="LP-001-16G", name="16GB",
        money_amount=Decimal("5999.00"), currency="CNY", sale_status="active",
        variant_attributes_json={},
    )
    inventory = CatalogInventory(sku=sku, on_hand_quantity=5, reserved_quantity=0, version=0)
    session.add_all([category, product, sku, inventory])
    thread = ConversationThread(
        id="thread-1", user_id="user-1", client_thread_id="thread-1", status="active",
        metadata_json={}, created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )
    recommendation = RecommendationResult(
        outcome="recommended", ranking_policy_version="v1", request_summary="demo",
        structured_constraints=LaptopConstraints(),
        recommendations=[Recommendation(
            product_id=product.id, sku_id=sku.id, product_name=product.name, sku_name=sku.name,
            money=Money(amount="5999", currency="CNY"), specifications=[], score=90,
            score_breakdown=[], availability=AvailabilityView(
                sale_status="active", available_quantity=5, in_stock=True
            ), reason="match",
        )],
    )
    run = AgentRun(
        id="run-1", thread=thread, user_id="user-1", operation="chat", mode="multi",
        status="completed", request_id="request-1", trace_id="trace-1", request_json={},
        result_json={"recommendation": recommendation.model_dump(mode="json")}, usage_json={},
        tool_call_records_json=[], metadata_json={}, started_at=datetime.now(timezone.utc),
    )
    session.add_all([thread, run])
    session.commit()
    return sku.id


def test_structured_pending_action_confirm_merges_and_replays():
    session = make_session()
    sku_id = seed_recommendation(session)
    view = create_add_to_cart_pending_action(
        session, user_id="user-1", thread_id="thread-1", source_run_id="run-1",
        sku_id=sku_id, quantity=2,
    )
    assert view.preview.kind == "catalog_sku"
    assert view.version == 1
    assert view.editable_fields[0].max_value == 20
    session.commit()

    result = confirm_add_to_cart(
        session, pending_action_id=view.pending_action_id, user_id="user-1", thread_id="thread-1",
        expected_version=1,
    )
    session.commit()
    assert result.cart_item is not None
    assert result.cart_item.quantity == 2
    assert result.current_money.amount == "5999.00"
    assert list_cart_items(session, user_id="user-1")[0].quantity == 2
    assert result.pending_action.status == "confirmed"
    assert result.requested_quantity == 2
    assert result.cart_quantity == 2

    replay = confirm_add_to_cart(
        session, pending_action_id=view.pending_action_id, user_id="user-1", thread_id="thread-1",
        expected_version=1,
    )
    assert replay.idempotent_replay is True
    assert list_cart_items(session, user_id="user-1")[0].quantity == 2


def test_recommendation_authority_rejects_other_sku_and_owner():
    session = make_session()
    sku_id = seed_recommendation(session)
    with __import__("pytest").raises(PendingActionServiceError) as exc_info:
        create_add_to_cart_pending_action(
            session, user_id="user-2", thread_id="thread-1", source_run_id="run-1",
            sku_id=sku_id, quantity=1,
        )
    assert exc_info.value.code == "recommendation_not_found"


def test_price_change_is_reported_without_writing_snapshot_to_cart():
    session = make_session()
    sku_id = seed_recommendation(session)
    view = create_add_to_cart_pending_action(
        session, user_id="user-1", thread_id="thread-1", source_run_id="run-1",
        sku_id=sku_id, quantity=1,
    )
    session.commit()
    session.get(CatalogSku, sku_id).money_amount = Decimal("6100.00")
    session.commit()

    result = confirm_add_to_cart(
        session, pending_action_id=view.pending_action_id, user_id="user-1", thread_id="thread-1",
        expected_version=1,
    )
    assert result.price_changed is True
    assert result.current_money.amount == "6100.00"
    assert result.cart_item.unit_money.amount == "6100.00"


def test_inventory_shortage_keeps_action_pending():
    session = make_session()
    sku_id = seed_recommendation(session)
    view = create_add_to_cart_pending_action(
        session, user_id="user-1", thread_id="thread-1", source_run_id="run-1",
        sku_id=sku_id, quantity=2,
    )
    session.commit()
    session.get(CatalogInventory, sku_id).on_hand_quantity = 1
    session.commit()

    with __import__("pytest").raises(PendingActionServiceError) as exc_info:
        confirm_add_to_cart(
            session, pending_action_id=view.pending_action_id, user_id="user-1", thread_id="thread-1",
            expected_version=1,
        )
    assert exc_info.value.code == "insufficient_inventory"
    assert session.get(PendingAction, view.pending_action_id).status == "pending"


def test_legacy_pending_action_view_uses_compatibility_preview():
    session = make_session()
    from app.db.models import PendingAction, Product

    session.add(Product(
        product_id="LEGACY-1", name="Legacy Keyboard", category="Keyboards",
        price=Decimal("99.00"), in_stock=True,
    ))
    action = PendingAction(
        id="legacy-action", user_id="user-1", thread_id="thread-1", action_type="add_to_cart",
        payload_json={"product_id": "LEGACY-1", "quantity": 1}, risk_class="high",
        preview_text="Legacy", status="pending", metadata_json={}, version=1, result_json={},
    )
    session.add(action)
    session.commit()
    view = pending_action_to_view(session, action)
    assert view.preview.kind == "legacy_product"
    assert view.preview.legacy_product_id == "LEGACY-1"
    assert view.preview.unit_money_snapshot is None
    assert view.preview.availability_snapshot is None


def test_catalog_preview_is_creation_snapshot_not_live_requery():
    session = make_session()
    sku_id = seed_recommendation(session)
    view = create_add_to_cart_pending_action(session, user_id="user-1", thread_id="thread-1", source_run_id="run-1", sku_id=sku_id, quantity=1)
    session.commit()
    product = session.scalar(select(CatalogProduct).where(CatalogProduct.id == view.preview.product_id))
    product.name = "Renamed after action"
    session.commit()
    refreshed = pending_action_to_view(session, session.get(PendingAction, view.pending_action_id))
    assert refreshed.preview.product_name == "Demo Laptop"


def test_terminal_inactive_error_replays_without_catalog_write():
    session = make_session()
    sku_id = seed_recommendation(session)
    view = create_add_to_cart_pending_action(session, user_id="user-1", thread_id="thread-1", source_run_id="run-1", sku_id=sku_id, quantity=1)
    session.commit()
    session.get(CatalogProduct, view.preview.product_id).sale_status = "inactive"
    session.commit()
    with __import__("pytest").raises(PendingActionServiceError) as first:
        confirm_add_to_cart(session, pending_action_id=view.pending_action_id, user_id="user-1", thread_id="thread-1", expected_version=1)
    assert first.value.code == "product_inactive" and first.value.persisted_terminal
    session.commit()
    with __import__("pytest").raises(PendingActionServiceError) as replay:
        confirm_add_to_cart(session, pending_action_id=view.pending_action_id, user_id="user-1", thread_id="thread-1", expected_version=1)
    assert replay.value.code == "product_inactive" and replay.value.idempotent_replay
