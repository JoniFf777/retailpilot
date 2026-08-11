from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy import event

from app.catalog.models import CatalogCategory, CatalogInventory, CatalogProduct, CatalogSku
from app.repositories.shopmind_cart import get_cart_response, upsert_cart_item
from app.services.cart import (
    CartServiceError,
    clear_user_cart,
    delete_cart_item_by_id,
    update_cart_item,
)
from tests.cart.test_phase2a_service import make_session, seed_recommendation


def test_cart_summary_and_current_price_are_decimal_based():
    session = make_session()
    sku_id = seed_recommendation(session)
    upsert_cart_item(session, user_id="user-1", sku_id=sku_id, quantity=2)
    session.commit()

    response = get_cart_response(session, user_id="user-1")
    assert response.item_count == 1
    assert response.total_quantity == 2
    assert response.subtotal is not None
    assert response.subtotal.amount == "11998.00"
    assert response.currency == "CNY"
    assert response.warnings == []


def test_cart_summary_mixed_currency_is_not_aggregated_and_reports_warning():
    session = make_session()
    first_sku_id = seed_recommendation(session)
    category = session.scalar(select(CatalogCategory).where(CatalogCategory.code == "laptop"))
    product = CatalogProduct(
        id=uuid4(), product_code="LP-EUR", category_id=category.id,
        brand="ShopMind", name="Euro Laptop", sale_status="active", attributes_json={},
    )
    second_sku = CatalogSku(
        id=uuid4(), product=product, sku_code="LP-EUR-16G", name="16GB",
        money_amount=Decimal("100.00"), currency="EUR", sale_status="active", variant_attributes_json={},
    )
    session.add_all([
        product,
        second_sku,
        CatalogInventory(sku=second_sku, on_hand_quantity=2, reserved_quantity=0, version=0),
    ])
    session.commit()
    upsert_cart_item(session, user_id="user-1", sku_id=first_sku_id, quantity=1)
    upsert_cart_item(session, user_id="user-1", sku_id=second_sku.id, quantity=1)
    session.commit()

    response = get_cart_response(session, user_id="user-1")
    assert response.subtotal is None and response.currency is None
    assert any(warning.code == "mixed_currency" for warning in response.warnings)


def test_cart_summary_query_count_is_constant_for_items():
    session = make_session()
    sku_id = seed_recommendation(session)
    upsert_cart_item(session, user_id="user-1", sku_id=sku_id, quantity=1)
    session.commit()
    statements: list[str] = []
    bind = session.get_bind()

    def count_sql(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    event.listen(bind, "before_cursor_execute", count_sql)
    try:
        get_cart_response(session, user_id="user-1")
    finally:
        event.remove(bind, "before_cursor_execute", count_sql)
    assert len(statements) == 1


def test_update_locks_owned_item_checks_inventory_and_only_flushes():
    session = make_session()
    sku_id = seed_recommendation(session)
    item = upsert_cart_item(session, user_id="user-1", sku_id=sku_id, quantity=1)
    session.commit()
    inventory = session.get(CatalogInventory, sku_id)
    before_inventory = (inventory.on_hand_quantity, inventory.reserved_quantity, inventory.version)

    result = update_cart_item(
        session,
        user_id="user-1",
        cart_item_id=item.id,
        expected_version=1,
        quantity=3,
    )
    assert result.item.quantity == 3
    assert result.item.version == 2
    assert session.get(CatalogInventory, sku_id).on_hand_quantity == before_inventory[0]
    assert (
        session.get(CatalogInventory, sku_id).on_hand_quantity,
        session.get(CatalogInventory, sku_id).reserved_quantity,
        session.get(CatalogInventory, sku_id).version,
    ) == before_inventory
    session.rollback()
    assert session.scalar(select(type(item)).where(type(item).id == item.id)).quantity == 1


@pytest.mark.parametrize(
    ("quantity", "code"),
    [(0, "invalid_quantity"), (21, "cart_quantity_limit")],
)
def test_update_quantity_boundaries_are_typed(quantity, code):
    session = make_session()
    sku_id = seed_recommendation(session)
    item = upsert_cart_item(session, user_id="user-1", sku_id=sku_id, quantity=1)
    session.commit()
    with pytest.raises(CartServiceError) as exc_info:
        update_cart_item(
            session,
            user_id="user-1",
            cart_item_id=item.id,
            expected_version=1,
            quantity=quantity,
        )
    assert exc_info.value.code == code
    session.rollback()


def test_update_owner_version_and_inventory_errors():
    session = make_session()
    sku_id = seed_recommendation(session)
    item = upsert_cart_item(session, user_id="user-1", sku_id=sku_id, quantity=1)
    session.commit()

    with pytest.raises(CartServiceError) as not_found:
        update_cart_item(session, user_id="user-2", cart_item_id=item.id, expected_version=1, quantity=2)
    assert not_found.value.code == "cart_item_not_found"
    with pytest.raises(CartServiceError) as conflict:
        update_cart_item(session, user_id="user-1", cart_item_id=item.id, expected_version=99, quantity=2)
    assert conflict.value.code == "cart_version_conflict"

    inventory = session.get(CatalogInventory, sku_id)
    inventory.on_hand_quantity = 0
    session.commit()
    with pytest.raises(CartServiceError) as shortage:
        update_cart_item(session, user_id="user-1", cart_item_id=item.id, expected_version=1, quantity=1)
    assert shortage.value.code == "insufficient_inventory"
    assert shortage.value.details.available_quantity == 0


def test_update_rejects_inactive_and_missing_inventory():
    session = make_session()
    sku_id = seed_recommendation(session)
    item = upsert_cart_item(session, user_id="user-1", sku_id=sku_id, quantity=1)
    session.commit()
    product = session.scalar(select(CatalogProduct).where(CatalogProduct.id == session.get(CatalogSku, sku_id).product_id))
    product.sale_status = "inactive"
    session.commit()
    with pytest.raises(CartServiceError) as inactive:
        update_cart_item(session, user_id="user-1", cart_item_id=item.id, expected_version=1, quantity=1)
    assert inactive.value.code == "product_inactive"

    product.sale_status = "active"
    session.delete(session.get(CatalogInventory, sku_id))
    session.commit()
    with pytest.raises(CartServiceError) as missing:
        update_cart_item(session, user_id="user-1", cart_item_id=item.id, expected_version=1, quantity=1)
    assert missing.value.code == "inventory_missing"


def test_delete_and_clear_are_idempotent_and_owner_scoped():
    session = make_session()
    sku_id = seed_recommendation(session)
    first = upsert_cart_item(session, user_id="user-1", sku_id=sku_id, quantity=1)
    second = upsert_cart_item(session, user_id="user-2", sku_id=sku_id, quantity=1)
    session.commit()
    delete_cart_item_by_id(session, user_id="user-2", cart_item_id=first.id)
    session.commit()
    assert session.get(type(first), first.id) is not None
    delete_cart_item_by_id(session, user_id="user-1", cart_item_id=first.id)
    session.commit()
    delete_cart_item_by_id(session, user_id="user-1", cart_item_id=first.id)
    session.commit()
    clear_user_cart(session, user_id="user-1")
    session.commit()
    assert session.get(type(second), second.id) is not None
    clear_user_cart(session, user_id="user-2")
    session.commit()
    assert session.get(type(second), second.id) is None


def test_clear_does_not_touch_legacy_cart():
    from app.db.models import CartItem, Product

    session = make_session()
    sku_id = seed_recommendation(session)
    upsert_cart_item(session, user_id="user-1", sku_id=sku_id, quantity=1)
    legacy_product = Product(
        product_id="LEGACY-CART-1", name="Legacy", category="Keyboards",
        price=Decimal("10.00"), in_stock=True,
    )
    legacy_item = CartItem(user_id="user-1", product_id=legacy_product.product_id, quantity=1)
    session.add_all([legacy_product, legacy_item])
    session.commit()
    clear_user_cart(session, user_id="user-1")
    session.commit()
    assert session.get(CartItem, legacy_item.id) is not None
