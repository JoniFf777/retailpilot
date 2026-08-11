"""Real PostgreSQL acceptance checks for the Phase 2A PendingAction boundary.

Run only against a disposable database with ``RUN_POSTGRES_INTEGRATION=1`` and
``TEST_DATABASE_URL`` set.  The suite never creates or drops the database.
"""

from __future__ import annotations

import os
import threading
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.catalog.models import CatalogCategory, CatalogInventory, CatalogProduct, CatalogSku
from app.db.base import Base
from app.db.models import AgentRun, ConversationThread, PendingAction
from app.schemas.recommendation import AvailabilityView, LaptopConstraints, Money, Recommendation, RecommendationResult
from app.services.pending_actions import (
    PendingActionServiceError,
    cancel_pending_action,
    confirm_add_to_cart,
    create_add_to_cart_pending_action,
    get_pending_action_view,
)


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_INTEGRATION") != "1" or not os.getenv("TEST_DATABASE_URL"),
    reason="set RUN_POSTGRES_INTEGRATION=1 and TEST_DATABASE_URL for real PostgreSQL acceptance",
)


@pytest.fixture(scope="module")
def db_factory():
    engine = create_engine(os.environ["TEST_DATABASE_URL"], pool_pre_ping=True)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    yield factory
    engine.dispose()


def _seed(factory: sessionmaker, *, user_id: str = "pg-user", thread_id: str = "pg-thread") -> tuple[str, str]:
    session: Session = factory()
    category = CatalogCategory(id=uuid4(), code=f"laptop-{uuid4().hex[:8]}", name="Laptop", status="active")
    product = CatalogProduct(id=uuid4(), product_code=f"PG-{uuid4().hex[:8]}", category=category, brand="ShopMind", name="PG Laptop", sale_status="active", attributes_json={})
    sku = CatalogSku(id=uuid4(), product=product, sku_code=f"PG-SKU-{uuid4().hex[:8]}", name="16GB", money_amount=Decimal("5999.00"), currency="CNY", sale_status="active", variant_attributes_json={})
    inventory = CatalogInventory(sku=sku, on_hand_quantity=20, reserved_quantity=0, version=0)
    thread = ConversationThread(id=thread_id, user_id=user_id, client_thread_id=thread_id, status="active", metadata_json={}, created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc))
    recommendation = RecommendationResult(outcome="recommended", ranking_policy_version="v1", request_summary="pg", structured_constraints=LaptopConstraints(), recommendations=[Recommendation(product_id=product.id, sku_id=sku.id, product_name=product.name, sku_name=sku.name, money=Money(amount="5999", currency="CNY"), specifications=[], score=90, score_breakdown=[], availability=AvailabilityView(sale_status="active", available_quantity=20, in_stock=True), reason="match")])
    run = AgentRun(id=f"pg-run-{uuid4().hex}", thread=thread, user_id=user_id, operation="chat", mode="multi", status="completed", request_id=uuid4().hex, trace_id=uuid4().hex, request_json={}, result_json={"recommendation": recommendation.model_dump(mode="json")}, usage_json={}, tool_call_records_json=[], metadata_json={}, started_at=datetime.now(timezone.utc))
    session.add_all([category, product, sku, inventory, thread, run])
    session.commit()
    session.close()
    return str(sku.id), run.id


def _create(factory: sessionmaker, *, user_id: str, thread_id: str, sku_id: str, run_id: str, quantity: int = 1):
    session: Session = factory()
    view = create_add_to_cart_pending_action(session, user_id=user_id, thread_id=thread_id, source_run_id=run_id, sku_id=uuid4() if False else __import__("uuid").UUID(sku_id), quantity=quantity)
    session.commit()
    session.close()
    return view


def test_postgres_resolution_replay_and_conflict(db_factory):
    thread_id = f"pg-thread-{uuid4().hex}"
    sku_id, run_id = _seed(db_factory, user_id="pg-user", thread_id=thread_id)
    view = _create(db_factory, user_id="pg-user", thread_id=thread_id, sku_id=sku_id, run_id=run_id)
    first_session: Session = db_factory()
    first = confirm_add_to_cart(first_session, pending_action_id=view.pending_action_id, user_id="pg-user", thread_id=thread_id, expected_version=1)
    first_session.commit()
    replay = confirm_add_to_cart(first_session, pending_action_id=view.pending_action_id, user_id="pg-user", thread_id=thread_id, expected_version=1)
    assert replay.idempotent_replay and replay.cart_quantity == first.cart_quantity
    with pytest.raises(PendingActionServiceError) as conflict:
        confirm_add_to_cart(first_session, pending_action_id=view.pending_action_id, user_id="pg-user", thread_id=thread_id, expected_version=1, updated_fields={"quantity": 2})
    assert conflict.value.code == "action_resolution_conflict"
    first_session.rollback(); first_session.close()


def test_postgres_confirm_cancel_race_has_one_terminal_state(db_factory):
    thread_id = f"race-{uuid4().hex}"
    sku_id, run_id = _seed(db_factory, user_id="race-user", thread_id=thread_id)
    view = _create(db_factory, user_id="race-user", thread_id=thread_id, sku_id=sku_id, run_id=run_id)
    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def confirm_worker():
        session = db_factory()
        barrier.wait()
        try:
            confirm_add_to_cart(session, pending_action_id=view.pending_action_id, user_id="race-user", thread_id=thread_id, expected_version=1)
            session.commit(); outcomes.append("confirmed")
        except PendingActionServiceError as exc:
            session.rollback(); outcomes.append(exc.code)
        finally:
            session.close()

    def cancel_worker():
        session = db_factory()
        barrier.wait()
        try:
            cancel_pending_action(session, pending_action_id=view.pending_action_id, user_id="race-user", thread_id=thread_id, expected_version=1)
            session.commit(); outcomes.append("cancelled")
        except PendingActionServiceError as exc:
            session.rollback(); outcomes.append(exc.code)
        finally:
            session.close()

    threads = [threading.Thread(target=confirm_worker), threading.Thread(target=cancel_worker)]
    [thread.start() for thread in threads]
    [thread.join(timeout=30) for thread in threads]
    assert len(outcomes) == 2
    assert sum(item in {"confirmed", "cancelled"} for item in outcomes) == 1
    assert any(item in {"action_resolution_conflict", "version_conflict"} for item in outcomes)


def test_postgres_two_actions_same_sku_serialize_cart_quantity(db_factory):
    thread_id = f"same-sku-{uuid4().hex}"
    sku_id, run_id = _seed(db_factory, user_id="same-sku-user", thread_id=thread_id)
    first = _create(db_factory, user_id="same-sku-user", thread_id=thread_id, sku_id=sku_id, run_id=run_id, quantity=15)
    second = _create(db_factory, user_id="same-sku-user", thread_id=thread_id, sku_id=sku_id, run_id=run_id, quantity=15)
    results: list[str] = []
    barrier = threading.Barrier(2)

    def worker(action_id: str):
        s = db_factory(); barrier.wait()
        try:
            confirm_add_to_cart(s, pending_action_id=action_id, user_id="same-sku-user", thread_id=thread_id, expected_version=1)
            s.commit(); results.append("confirmed")
        except PendingActionServiceError as exc:
            s.rollback(); results.append(exc.code)
        finally: s.close()

    threads = [threading.Thread(target=worker, args=(first.pending_action_id,)), threading.Thread(target=worker, args=(second.pending_action_id,))]
    [thread.start() for thread in threads]; [thread.join(timeout=30) for thread in threads]
    assert len(results) == 2 and results.count("confirmed") == 1
    assert results.count("cart_quantity_limit") + results.count("insufficient_inventory") == 1


def test_postgres_get_expire_serializes_with_confirm(db_factory):
    thread_id = f"expire-{uuid4().hex}"
    sku_id, run_id = _seed(db_factory, user_id="expire-user", thread_id=thread_id)
    view = _create(db_factory, user_id="expire-user", thread_id=thread_id, sku_id=sku_id, run_id=run_id)
    session = db_factory()
    action = session.get(PendingAction, view.pending_action_id)
    action.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    session.commit(); session.close()
    barrier = threading.Barrier(2); outcomes: list[str] = []

    def get_worker():
        s = db_factory(); barrier.wait()
        try:
            get_pending_action_view(s, pending_action_id=view.pending_action_id, user_id="expire-user", thread_id=thread_id); s.commit(); outcomes.append("expired")
        finally: s.close()

    def confirm_worker():
        s = db_factory(); barrier.wait()
        try:
            confirm_add_to_cart(s, pending_action_id=view.pending_action_id, user_id="expire-user", thread_id=thread_id, expected_version=1); s.commit(); outcomes.append("confirmed")
        except PendingActionServiceError as exc:
            s.rollback(); outcomes.append(exc.code)
        finally: s.close()

    threads = [threading.Thread(target=get_worker), threading.Thread(target=confirm_worker)]
    [thread.start() for thread in threads]; [thread.join(timeout=30) for thread in threads]
    assert len(outcomes) == 2 and "expired" in outcomes
    assert "confirmed" not in outcomes


def test_postgres_rollback_after_cart_flush_restores_pending_action(db_factory):
    thread_id = f"rollback-{uuid4().hex}"
    sku_id, run_id = _seed(db_factory, user_id="rollback-user", thread_id=thread_id)
    view = _create(db_factory, user_id="rollback-user", thread_id=thread_id, sku_id=sku_id, run_id=run_id)
    session = db_factory()
    result = confirm_add_to_cart(session, pending_action_id=view.pending_action_id, user_id="rollback-user", thread_id=thread_id, expected_version=1)
    assert result.cart_item is not None
    session.rollback()
    assert session.scalar(select(PendingAction).where(PendingAction.id == view.pending_action_id)).status == "pending"
    session.close()
