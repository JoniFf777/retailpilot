"""PostgreSQL acceptance for task action atomicity, replay and races."""

from __future__ import annotations

import os
import threading
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.orm import Session, sessionmaker

if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
    pytest.skip("set RUN_POSTGRES_INTEGRATION=1", allow_module_level=True)

from app.catalog.models import (
    CatalogCategory,
    CatalogInventory,
    CatalogProduct,
    CatalogSku,
)
from app.cart.models import ShopMindCartItem
from app.core.settings import get_settings
from app.db.models import Customer, Order
from app.shopping_tasks.actions import ShoppingTaskActionError, confirm_task_action
from app.shopping_tasks.contracts import (
    Fact,
    ShoppingTaskRequest,
    SourceRef,
    canonical_fingerprint,
)
from app.shopping_tasks.models import (
    AfterSalesDraft,
    ShoppingTask,
    ShoppingTaskAction,
    ShoppingTaskArtifact,
)
from app.shopping_tasks.repository import claim_task, create_task, refresh_task_status


@pytest.fixture(scope="module")
def db_factory():
    engine_url = get_settings().test_database_url
    schema = f"shopmind_task_actions_{uuid4().hex}"
    bootstrap = create_engine(engine_url, pool_pre_ping=True)
    with bootstrap.connect() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        connection.execute(
            text(
                f'CREATE TABLE "{schema}".alembic_version '
                "(version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
            )
        )
        connection.commit()
    bootstrap.dispose()
    engine = create_engine(engine_url, pool_pre_ping=True)

    @event.listens_for(engine, "connect")
    def _set_private_search_path(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute(f'SET search_path TO "{schema}", public')
        cursor.close()

    @event.listens_for(engine, "checkout")
    def _restore_private_search_path(dbapi_connection, _connection_record, _proxy):
        cursor = dbapi_connection.cursor()
        cursor.execute(f'SET search_path TO "{schema}", public')
        cursor.close()

    with engine.connect() as connection:
        config = Config("alembic.ini")
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        with engine.connect() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
            connection.commit()
        engine.dispose()


def _seed_skus(session: Session, *, inactive_index: int | None = None):
    category = CatalogCategory(
        code=f"task-action-{uuid4().hex[:10]}",
        name="Task Action",
        status="active",
    )
    rows = []
    for index, slot in enumerate(("laptop", "monitor", "dock")):
        product = CatalogProduct(
            product_code=f"TA-P-{uuid4().hex[:10]}",
            category=category,
            brand="ShopMind",
            name=f"Task {slot}",
            sale_status="active",
            attributes_json={},
        )
        sku = CatalogSku(
            product=product,
            sku_code=f"TA-{slot.upper()}-{uuid4().hex[:8]}",
            name=slot,
            money_amount=Decimal(str(1000 + index * 100)),
            currency="CNY",
            sale_status="inactive" if inactive_index == index else "active",
            variant_attributes_json={},
        )
        inventory = CatalogInventory(
            sku=sku,
            on_hand_quantity=5,
            reserved_quantity=0,
            version=0,
        )
        session.add_all([product, sku, inventory])
        rows.append((slot, sku))
    session.flush()
    return rows


def _seed_bundle_action(factory, *, owner_id: str, inactive_index: int | None = None):
    session: Session = factory()
    rows = _seed_skus(session, inactive_index=inactive_index)
    request = ShoppingTaskRequest(
        kind="bundle_selection",
        goal_text="预算 5000 元三件套",
        known_facts=[
            Fact(
                key="budget",
                value=5000,
                source_ref=SourceRef(
                    source="user_reported",
                    source_id="action-test-budget",
                    verified=False,
                ),
            )
        ],
    )
    task = create_task(
        session,
        owner_id=owner_id,
        request=request,
        idempotency_key=f"create-{uuid4().hex}",
    )
    items = [
        {
            "slot": slot,
            "sku_id": str(sku.id),
            "sku_code": sku.sku_code,
            "price": str(sku.money_amount),
            "quantity": 1,
        }
        for slot, sku in rows
    ]
    output = {
        "outcome": "recommended",
        "bundle_proposal": {
            "outcome": "recommended",
            "options": [{"items": items, "total": "3300.00", "currency": "CNY"}],
        },
    }
    artifact = ShoppingTaskArtifact(
        task_id=task.id,
        plan_revision=task.active_plan_revision,
        kind="task_result",
        branch="compose_result",
        payload_json=output,
        input_fingerprint=canonical_fingerprint(output),
        source_refs_json=[],
        evidence_versions_json=[],
        verification_status="passed",
    )
    session.add(artifact)
    session.flush()
    action = ShoppingTaskAction(
        task_id=task.id,
        artifact_id=artifact.id,
        action_type="add_bundle_to_cart",
        goal_version=task.goal_version,
        plan_revision=task.active_plan_revision,
        action_version=1,
        payload_json=output,
        status="pending",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    task.status = "awaiting_approval"
    task.output_json = output
    session.add(action)
    session.commit()
    result = (task.id, task.version, action.id, [sku.id for _, sku in rows])
    session.close()
    return result


def _confirm(factory, *, owner_id, task_id, action_id, version, key, confirmed=True):
    session: Session = factory()
    try:
        result = confirm_task_action(
            session,
            owner_id=owner_id,
            task_id=task_id,
            action_id=action_id,
            expected_version=version,
            confirmed=confirmed,
            idempotency_key=key,
        )
        session.commit()
        return ("ok", result)
    except ShoppingTaskActionError as exc:
        session.rollback()
        return ("error", exc.code)
    finally:
        session.close()


def test_bundle_confirm_replay_and_single_item_failure_rolls_back(db_factory) -> None:
    owner = f"bundle-action-{uuid4().hex}"
    task_id, version, action_id, _sku_ids = _seed_bundle_action(
        db_factory, owner_id=owner
    )
    first = _confirm(
        db_factory,
        owner_id=owner,
        task_id=task_id,
        action_id=action_id,
        version=version,
        key="bundle-confirm-replay",
    )
    replay = _confirm(
        db_factory,
        owner_id=owner,
        task_id=task_id,
        action_id=action_id,
        version=version,
        key="bundle-confirm-replay",
    )
    assert first[0] == replay[0] == "ok"
    assert first[1] == replay[1]
    session = db_factory()
    rows = list(
        session.scalars(
            select(ShopMindCartItem).where(ShopMindCartItem.user_id == owner)
        ).all()
    )
    assert len(rows) == 3 and {row.quantity for row in rows} == {1}
    session.close()

    failed_owner = f"bundle-failure-{uuid4().hex}"
    failed_task, failed_version, failed_action, _ = _seed_bundle_action(
        db_factory,
        owner_id=failed_owner,
        inactive_index=2,
    )
    failed = _confirm(
        db_factory,
        owner_id=failed_owner,
        task_id=failed_task,
        action_id=failed_action,
        version=failed_version,
        key="bundle-failure",
    )
    assert failed == ("error", "catalog_changed_repreview_required")
    session = db_factory()
    assert (
        session.scalar(
            select(ShopMindCartItem).where(ShopMindCartItem.user_id == failed_owner)
        )
        is None
    )
    assert session.get(ShoppingTaskAction, failed_action).status == "pending"
    session.close()


def test_concurrent_bundle_confirmation_and_cancel_are_serialized(db_factory) -> None:
    owner = f"bundle-concurrent-{uuid4().hex}"
    task_id, version, action_id, _ = _seed_bundle_action(db_factory, owner_id=owner)
    barrier = threading.Barrier(2)
    outcomes = []

    def run(key: str, confirmed: bool) -> None:
        barrier.wait()
        outcomes.append(
            _confirm(
                db_factory,
                owner_id=owner,
                task_id=task_id,
                action_id=action_id,
                version=version,
                key=key,
                confirmed=confirmed,
            )
        )

    threads = [
        threading.Thread(target=run, args=("race-confirm", True)),
        threading.Thread(target=run, args=("race-cancel", False)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)
    assert all(not thread.is_alive() for thread in threads)
    assert sum(status == "ok" for status, _ in outcomes) == 1
    session = db_factory()
    action = session.get(ShoppingTaskAction, action_id)
    cart_rows = list(
        session.scalars(
            select(ShopMindCartItem).where(ShopMindCartItem.user_id == owner)
        ).all()
    )
    if action.status == "confirmed":
        assert len(cart_rows) == 3
    else:
        assert action.status == "cancelled" and cart_rows == []
    session.close()


def test_after_sales_draft_is_owner_bound_and_replayed_once(db_factory) -> None:
    owner = f"draft-owner-{uuid4().hex}"
    session: Session = db_factory()
    customer = Customer(
        customer_id=owner,
        email=f"{owner}@example.com",
        name="Draft Owner",
        city="Shanghai",
        state="Shanghai",
        segment="Consumer",
    )
    order = Order(
        order_id=f"ORDER-{uuid4().hex[:10]}",
        customer=customer,
        order_date=date.today(),
        status="Delivered",
        total_amount=Decimal("100.00"),
    )
    session.add_all([customer, order])
    task = create_task(
        session,
        owner_id=owner,
        request=ShoppingTaskRequest(
            kind="after_sales_assessment",
            goal_text="保存售后草稿",
        ),
        idempotency_key="draft-create",
    )
    output = {
        "outcome": "conditional",
        "assessment": {"outcome": "conditional", "missing_facts": ["delivered_at"]},
        "order": {"order_id": order.order_id, "owner_id": owner},
    }
    artifact = ShoppingTaskArtifact(
        task_id=task.id,
        plan_revision=1,
        kind="task_result",
        branch="compose_result",
        payload_json=output,
        input_fingerprint=canonical_fingerprint(output),
        source_refs_json=[],
        evidence_versions_json=[],
        verification_status="passed",
    )
    session.add(artifact)
    session.flush()
    action = ShoppingTaskAction(
        task_id=task.id,
        artifact_id=artifact.id,
        action_type="save_after_sales_draft",
        goal_version=1,
        plan_revision=1,
        action_version=1,
        payload_json=output,
        status="pending",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    task.status = "awaiting_approval"
    session.add(action)
    session.commit()
    version = task.version
    task_id, action_id = task.id, action.id
    session.close()

    first = _confirm(
        db_factory,
        owner_id=owner,
        task_id=task_id,
        action_id=action_id,
        version=version,
        key="draft-confirm",
    )
    replay = _confirm(
        db_factory,
        owner_id=owner,
        task_id=task_id,
        action_id=action_id,
        version=version,
        key="draft-confirm",
    )
    assert first[0] == replay[0] == "ok"
    assert first[1] == replay[1]
    session = db_factory()
    drafts = list(
        session.scalars(
            select(AfterSalesDraft).where(AfterSalesDraft.owner_id == owner)
        ).all()
    )
    assert len(drafts) == 1
    assert drafts[0].order_id == order.order_id
    assert drafts[0].payload_json["draft_only"] is True
    session.close()


def test_rollback_drain_cancels_active_work_and_preserves_confirmed_cart(
    db_factory,
) -> None:
    owner = f"rollback-owner-{uuid4().hex}"
    confirmed_task, version, action_id, _ = _seed_bundle_action(
        db_factory,
        owner_id=owner,
    )
    result = _confirm(
        db_factory,
        owner_id=owner,
        task_id=confirmed_task,
        action_id=action_id,
        version=version,
        key="rollback-confirmed-fact",
    )
    assert result[0] == "ok"

    session: Session = db_factory()
    queued = create_task(
        session,
        owner_id=owner,
        request=ShoppingTaskRequest(
            kind="compatibility_diagnosis",
            goal_text="rollback drain",
        ),
        idempotency_key="rollback-active-task",
    )
    session.commit()
    claimed = claim_task(session, worker_id="rollback-worker", lease_seconds=30)
    assert claimed is not None and claimed[0].id == queued.id
    queued.cancel_requested = True
    refresh_task_status(session, task_id=queued.id)
    session.commit()
    refreshed = session.get(ShoppingTask, queued.id)
    assert refreshed.status == "cancelled"
    assert refreshed.lease_token is None and refreshed.lease_until is None
    cart_rows = list(
        session.scalars(
            select(ShopMindCartItem).where(ShopMindCartItem.user_id == owner)
        ).all()
    )
    assert len(cart_rows) == 3
    session.close()
