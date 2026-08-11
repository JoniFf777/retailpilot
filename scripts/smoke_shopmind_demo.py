"""Fail-closed smoke checks for the ShopMind offline core demo.

The default verification probes health/readiness, the frontend shell, current
migrations, the seeded catalog, and then exercises the server-owned
Recommendation -> PendingAction -> Cart -> Checkout -> Order -> Mock Payment
path. Passing ``--order-id --require-paid`` instead verifies a browser-created
order, including reservations, inventory, and exactly-one outbox event per
fact.
"""

from __future__ import annotations

import argparse
import json
from uuid import uuid4
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from sqlalchemy import func, select, text

from app.catalog.models import CatalogInventory, CatalogSku
from app.db.version import MIGRATION_HEAD
from app.orders.models import (
    ShopMindInventoryReservation,
    ShopMindOrder,
    ShopMindOrderItem,
)
from app.outbox.models import ShopMindOutboxEvent


REQUIRED_OPENAPI_PATHS = {
    "/api/checkout/preview",
    "/api/orders",
    "/api/orders/{order_id}",
    "/api/orders/{order_id}/payments",
}


class DemoSmokeError(RuntimeError):
    """A user-actionable demo readiness failure."""


def _assert_offline_demo_readiness(readiness: Any) -> None:
    if readiness.get("profile") != "offline-demo":
        raise DemoSmokeError(
            "Backend readiness is not the offline-demo profile; stop the old server "
            "or use a different backend port."
        )
    if readiness.get("ready") is not True or readiness.get("status") != "ready":
        raise DemoSmokeError("Backend readiness is not ready")


def _http_json(
    base_url: str,
    path: str,
    *,
    expected_status: int = 200,
    method: str = "GET",
    payload: Any | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, Any]:
    url = f"{base_url.rstrip('/')}{path}"
    request_headers = {"Accept": "application/json", **(headers or {})}
    body = None
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")
    try:
        with urlopen(
            Request(url, data=body, headers=request_headers, method=method), timeout=20
        ) as response:
            status = response.status
            body = response.read().decode("utf-8")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise DemoSmokeError(f"HTTP {exc.code} {path}: {body[:240]}") from exc
    except (OSError, URLError) as exc:
        raise DemoSmokeError(f"Cannot reach {path}: {exc.__class__.__name__}") from exc
    if status != expected_status:
        raise DemoSmokeError(f"HTTP {status} {path}; expected {expected_status}")
    try:
        return status, json.loads(body)
    except json.JSONDecodeError as exc:
        raise DemoSmokeError(f"{path} did not return JSON") from exc


def _session():
    from app.db.session import SessionLocal

    return SessionLocal()


def snapshot_inventory() -> dict[str, dict[str, int]]:
    session = _session()
    try:
        rows = session.execute(
            select(
                CatalogInventory.sku_id,
                CatalogInventory.on_hand_quantity,
                CatalogInventory.reserved_quantity,
                CatalogInventory.version,
            )
        ).all()
        return {
            str(sku_id): {
                "on_hand_quantity": int(on_hand),
                "reserved_quantity": int(reserved),
                "version": int(version),
            }
            for sku_id, on_hand, reserved, version in rows
        }
    finally:
        session.close()


def _assert_order_facts(
    order_id: str,
    *,
    user_id: str,
    initial_inventory: dict[str, dict[str, int]] | None,
) -> dict[str, Any]:
    from uuid import UUID

    try:
        parsed_order_id = UUID(order_id)
    except ValueError as exc:
        raise DemoSmokeError("--order-id must be a UUID") from exc

    session = _session()
    try:
        order = session.scalar(
            select(ShopMindOrder).where(
                ShopMindOrder.id == parsed_order_id,
                ShopMindOrder.user_id == user_id,
            )
        )
        if order is None:
            raise DemoSmokeError("Order was not found for the supplied demo user")
        if order.status != "paid":
            raise DemoSmokeError(f"Order state is {order.status}, expected paid")

        items = list(
            session.scalars(
                select(ShopMindOrderItem)
                .where(ShopMindOrderItem.order_id == order.id)
                .order_by(ShopMindOrderItem.id)
            )
        )
        attempts = list(
            session.execute(
                text(
                    "select status from shopmind_payment_attempts "
                    "where order_id = :order_id order by created_at, id"
                ),
                {"order_id": order.id},
            ).scalars()
        )
        if attempts != ["succeeded"]:
            raise DemoSmokeError(f"PaymentAttempt facts are {attempts}, expected one succeeded")

        reservations = list(
            session.scalars(
                select(ShopMindInventoryReservation)
                .where(
                    ShopMindInventoryReservation.order_item_id.in_(
                        [item.id for item in items]
                    )
                )
                .order_by(ShopMindInventoryReservation.id)
            )
        )
        if len(reservations) != len(items) or any(
            reservation.status != "consumed" for reservation in reservations
        ):
            raise DemoSmokeError("Every Order item must have one consumed reservation")

        inventory_facts: list[dict[str, Any]] = []
        for item, reservation in zip(items, reservations, strict=True):
            if reservation.sku_id != item.sku_id or reservation.quantity != item.quantity:
                raise DemoSmokeError("Reservation does not match its Order item")
            inventory = session.get(CatalogInventory, item.sku_id)
            if inventory is None:
                raise DemoSmokeError("Order SKU has no Inventory row")
            before = (initial_inventory or {}).get(str(item.sku_id))
            if before is None:
                raise DemoSmokeError("Missing pre-order Inventory snapshot for an Order SKU")
            expected_on_hand = before["on_hand_quantity"] - item.quantity
            expected_reserved = before["reserved_quantity"]
            expected_version = before["version"] + 2
            if (
                inventory.on_hand_quantity != expected_on_hand
                or inventory.reserved_quantity != expected_reserved
                or inventory.version != expected_version
            ):
                raise DemoSmokeError(
                    "Inventory facts do not equal one reservation plus one consume "
                    f"for SKU {item.sku_code_snapshot}"
                )
            inventory_facts.append(
                {
                    "sku_code": item.sku_code_snapshot,
                    "quantity": item.quantity,
                    "on_hand_quantity": inventory.on_hand_quantity,
                    "reserved_quantity": inventory.reserved_quantity,
                    "version": inventory.version,
                }
            )

        events = list(
            session.scalars(
                select(ShopMindOutboxEvent)
                .where(ShopMindOutboxEvent.aggregate_id == order.id)
                .order_by(ShopMindOutboxEvent.aggregate_sequence)
            )
        )
        event_types = [event.event_type for event in events]
        if (
            event_types.count("shopmind.order.created.v1") != 1
            or event_types.count("shopmind.payment.succeeded.v1") != 1
        ):
            raise DemoSmokeError(
                f"Outbox facts are {event_types}, expected one versioned order-created and payment-succeeded event"
            )
        if len(events) != 2:
            raise DemoSmokeError(f"Expected exactly two Order outbox events, found {len(events)}")

        return {
            "order_status": order.status,
            "payment_attempts": attempts,
            "reservations": [reservation.status for reservation in reservations],
            "inventory": inventory_facts,
            "outbox_event_types": event_types,
        }
    finally:
        session.close()


def run_smoke(
    *,
    backend_url: str,
    frontend_url: str,
    user_id: str,
    order_id: str | None = None,
    require_paid: bool = False,
    initial_inventory: dict[str, dict[str, int]] | None = None,
) -> dict[str, Any]:
    _, health = _http_json(backend_url, "/api/health")
    if health.get("status") != "ok":
        raise DemoSmokeError("Backend health response is not ok")

    _, readiness = _http_json(backend_url, "/api/health/readiness")
    _assert_offline_demo_readiness(readiness)

    _, openapi = _http_json(backend_url.replace("/api", ""), "/openapi.json")
    missing_paths = sorted(REQUIRED_OPENAPI_PATHS - set(openapi.get("paths", {})))
    if missing_paths:
        raise DemoSmokeError(f"OpenAPI is missing core paths: {', '.join(missing_paths)}")

    _, orders = _http_json(backend_url, f"/api/orders?user_id={user_id}")
    if not isinstance(orders.get("items"), list) or "next_cursor" not in orders:
        raise DemoSmokeError("Order list response shape is invalid")

    session = _session()
    try:
        migration = session.execute(text("select version_num from alembic_version")).scalar_one()
        active_skus = session.scalar(
            select(func.count()).select_from(CatalogSku).where(CatalogSku.sale_status == "active")
        ) or 0
        inventory_rows = session.scalar(select(func.count()).select_from(CatalogInventory)) or 0
    finally:
        session.close()
    if migration != MIGRATION_HEAD:
        raise DemoSmokeError(f"Migration is {migration}, expected {MIGRATION_HEAD}")
    if active_skus <= 0 or inventory_rows < active_skus:
        raise DemoSmokeError("Seeded ShopMind catalog/inventory is unavailable")

    # Frontend is HTML rather than JSON; keep this probe separate and explicit.
    try:
        with urlopen(Request(f"{frontend_url.rstrip('/')}/", headers={"Accept": "text/html"}), timeout=8) as response:
            frontend_status = response.status
            html = response.read().decode("utf-8", errors="replace")
    except (OSError, URLError) as exc:
        raise DemoSmokeError(f"Cannot reach frontend: {exc.__class__.__name__}") from exc
    if frontend_status != 200 or "<div id=\"root\">" not in html:
        raise DemoSmokeError("Frontend did not return the Vite application shell")

    facts = None
    exercised_order_id: str | None = None
    if order_id is None:
        # Exercise the same server-owned API sequence used by the browser demo.
        # The request body never contains force_success/scenario controls.
        thread_id = f"{user_id}-thread"
        chat_path = "/api/chat"
        _, chat = _http_json(
            backend_url,
            chat_path,
            method="POST",
            payload={
                "message": "laptop，预算 12000 元以内，主要用于 Java 开发，内存至少 16GB，希望尽量轻",
                "user_id": user_id,
                "thread_id": thread_id,
            },
        )
        recommendation = chat.get("recommendation")
        context = chat.get("recommendation_context") or {}
        recommendations = recommendation.get("recommendations") if isinstance(recommendation, dict) else None
        if (
            not isinstance(recommendation, dict)
            or recommendation.get("outcome") != "recommended"
            or not isinstance(recommendations, list)
            or not recommendations
            or not context.get("source_run_id")
        ):
            raise DemoSmokeError("Catalog recommendation response is not a usable structured result")
        selected = recommendations[0]
        sku_id = selected.get("sku_id")
        if not sku_id:
            raise DemoSmokeError("Recommendation did not expose a selectable sku_id")
        before = snapshot_inventory()
        _, pending = _http_json(
            backend_url,
            "/api/pending-actions/add-to-cart",
            method="POST",
            payload={
                "user_id": user_id,
                "thread_id": thread_id,
                "source_run_id": context["source_run_id"],
                "sku_id": sku_id,
                "quantity": 1,
            },
            expected_status=201,
        )
        pending_id = pending.get("pending_action_id")
        if not pending_id or pending.get("status") != "pending":
            raise DemoSmokeError("PendingAction response shape is invalid")
        _, confirmed = _http_json(
            backend_url,
            f"/api/pending-actions/{pending_id}/confirm",
            method="POST",
            payload={"user_id": user_id, "thread_id": thread_id, "expected_version": 1},
        )
        if (confirmed.get("pending_action") or {}).get("status") != "confirmed" or not confirmed.get("cart_item"):
            raise DemoSmokeError("PendingAction confirmation did not create a Cart item")
        _, preview = _http_json(
            backend_url,
            f"/api/checkout/preview?user_id={user_id}",
            method="POST",
            payload={},
        )
        if preview.get("can_create_order") is not True or not preview.get("checkout_token"):
            raise DemoSmokeError("Checkout Preview did not authorize the seeded Cart")
        order_key = f"shopmind-demo-order-{uuid4()}"
        _, created = _http_json(
            backend_url,
            f"/api/orders?user_id={user_id}",
            method="POST",
            headers={"Idempotency-Key": order_key},
            payload={"checkout_token": preview["checkout_token"]},
            expected_status=201,
        )
        order = created.get("order") or {}
        exercised_order_id = str(order.get("order_id") or "")
        if not exercised_order_id or order.get("status") != "pending_payment":
            raise DemoSmokeError("Create Order response did not create pending_payment Order")
        _, paid = _http_json(
            backend_url,
            f"/api/orders/{exercised_order_id}/payments?user_id={user_id}",
            method="POST",
            headers={"Idempotency-Key": f"shopmind-demo-payment-{uuid4()}"},
            payload={"provider": "mock", "payment_method_ref": "mock-web"},
        )
        paid_order = paid.get("order") or {}
        attempt = paid.get("payment_attempt") or {}
        if paid_order.get("status") != "paid" or attempt.get("status") != "succeeded":
            raise DemoSmokeError("Mock Payment API did not finalize the Order")
        facts = _assert_order_facts(
            exercised_order_id,
            user_id=user_id,
            initial_inventory=before,
        )
    elif require_paid:
        # The caller supplied the before-snapshot when it wants exact inventory
        # assertions for an already completed browser order.
        facts = _assert_order_facts(
            order_id,
            user_id=user_id,
            initial_inventory=initial_inventory,
        )
    if order_id:
        _, order = _http_json(backend_url, f"/api/orders/{order_id}?user_id={user_id}")
        _, payments = _http_json(backend_url, f"/api/orders/{order_id}/payments?user_id={user_id}")
        if order.get("order_id") != order_id or not isinstance(payments.get("items"), list):
            raise DemoSmokeError("Order/Payment response shape is invalid")
        if require_paid and facts is None:
            raise DemoSmokeError("--require-paid requires a pre-order Inventory snapshot")

    return {
        "status": "pass",
        "migration": migration,
        "active_skus": int(active_skus),
        "inventory_rows": int(inventory_rows),
        "exercised_order_id": exercised_order_id,
        "order_facts": facts,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify the ShopMind offline core demo.")
    parser.add_argument("--backend-url", default="http://127.0.0.1:8000")
    parser.add_argument("--frontend-url", default="http://127.0.0.1:5173")
    parser.add_argument("--user-id", default="demo-user")
    parser.add_argument("--order-id")
    parser.add_argument("--require-paid", action="store_true")
    parser.add_argument("--snapshot-inventory", action="store_true")
    parser.add_argument("--initial-inventory-json")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.snapshot_inventory:
            report: Any = {"status": "pass", "inventory": snapshot_inventory()}
        else:
            initial = None
            if args.initial_inventory_json:
                initial = json.loads(args.initial_inventory_json)
            report = run_smoke(
                backend_url=args.backend_url,
                frontend_url=args.frontend_url,
                user_id=args.user_id,
                order_id=args.order_id,
                require_paid=args.require_paid,
                initial_inventory=initial,
            )
        print(json.dumps(report, ensure_ascii=False) if args.json else report)
        return 0
    except Exception as exc:
        print(f"ShopMind demo smoke failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
