"""Shared reservation-release invariants for Cancel and Order Expiry."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.catalog.models import CatalogInventory
from app.repositories.inventory_reservations import mark_released
from app.repositories.shopmind_orders import get_order_item_reservations_for_update


class ReservationReleaseError(ValueError):
    """A reservation/inventory invariant failed before terminal transition."""

    def __init__(self, code: str = "reservation_inconsistent") -> None:
        super().__init__(code)
        self.code = code


def release_active_reservations(
    session: Session, *, order_id: UUID, released_at: datetime | None = None
) -> int:
    """Release active reservations after the caller's payment-safety gate.

    This helper intentionally does not inspect PaymentAttempts or mutate the
    Order status/Event. Cancel and Expiry own those decisions separately.
    """

    rows = get_order_item_reservations_for_update(session, order_id=order_id)
    if not rows or any(reservation is None for _, reservation in rows):
        raise ReservationReleaseError()
    reservations = [reservation for _, reservation in rows]
    for item, reservation in rows:
        if (
            reservation.sku_id != item.sku_id
            or reservation.quantity != item.quantity
            or reservation.status != "active"
        ):
            raise ReservationReleaseError()

    sku_ids = sorted({reservation.sku_id for reservation in reservations}, key=str)
    inventories = list(
        session.scalars(
            select(CatalogInventory)
            .where(CatalogInventory.sku_id.in_(sku_ids))
            .order_by(CatalogInventory.sku_id.asc())
            .with_for_update()
        ).all()
    )
    inventory_by_sku = {inventory.sku_id: inventory for inventory in inventories}
    if set(inventory_by_sku) != set(sku_ids):
        raise ReservationReleaseError()

    for reservation in sorted(reservations, key=lambda row: str(row.sku_id)):
        updated = session.execute(
            update(CatalogInventory)
            .where(
                CatalogInventory.sku_id == reservation.sku_id,
                CatalogInventory.reserved_quantity >= reservation.quantity,
            )
            .values(
                reserved_quantity=CatalogInventory.reserved_quantity - reservation.quantity,
                version=CatalogInventory.version + 1,
                updated_at=released_at or datetime.now(timezone.utc),
            )
            .returning(CatalogInventory.sku_id)
        ).scalar_one_or_none()
        if updated is None:
            raise ReservationReleaseError()

    for reservation in reservations:
        mark_released(session, reservation)
    return len(reservations)


__all__ = ["ReservationReleaseError", "release_active_reservations"]
