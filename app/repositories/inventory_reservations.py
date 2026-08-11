"""Reservation update helpers kept separate from Catalog inventory ownership."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.orders.models import ShopMindInventoryReservation


def mark_released(session: Session, reservation: ShopMindInventoryReservation) -> None:
    reservation.status = "released"
    reservation.released_at = datetime.now(timezone.utc)
    reservation.consumed_at = None
    session.flush()


def mark_consumed(session: Session, reservation: ShopMindInventoryReservation) -> None:
    reservation.status = "consumed"
    reservation.released_at = None
    reservation.consumed_at = datetime.now(timezone.utc)
    session.flush()
