"""Versioned, JSON-safe state for one owner's shopping decision thread."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ShoppingSessionState(BaseModel):
    """The latest validated recommendation request, not a transcript dump."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["shopmind.shopping-session-state.v1"] = (
        "shopmind.shopping-session-state.v1"
    )
    owner_id: str | None = None
    thread_id: str | None = None
    version: int = Field(default=0, ge=0)
    updated_at: datetime | None = None
    category: str | None = None
    budget_min: Decimal | None = Field(default=None, gt=0)
    budget_max: Decimal | None = Field(default=None, gt=0)
    budget_currency: str | None = None
    category_attributes: dict[str, Any] = Field(default_factory=dict)
    field_sources: dict[str, Literal["user", "preference", "inherited", "system"]] = (
        Field(default_factory=dict)
    )
    pending_questions: list[str] = Field(default_factory=list, max_length=5)
    candidate_sku_codes: list[str] = Field(default_factory=list, max_length=3)
    excluded_sku_codes: list[str] = Field(default_factory=list, max_length=20)
    candidate_expires_at: datetime | None = None

    @model_validator(mode="after")
    def validate_budget_range(self) -> "ShoppingSessionState":
        if (
            self.budget_min is not None
            and self.budget_max is not None
            and self.budget_min > self.budget_max
        ):
            raise ValueError("shopping session budget_min must not exceed budget_max")
        if self.updated_at is not None and self.updated_at.tzinfo is None:
            raise ValueError("shopping session updated_at must be timezone-aware")
        if (
            self.candidate_expires_at is not None
            and self.candidate_expires_at.tzinfo is None
        ):
            raise ValueError(
                "shopping session candidate_expires_at must be timezone-aware"
            )
        return self

    @property
    def candidates_are_current(self) -> bool:
        """Whether the candidate order is safe to use for ordinal follow-ups."""

        if self.candidate_expires_at is None:
            return True
        expires_at = self.candidate_expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return expires_at > datetime.now(timezone.utc)

    def current_candidate_sku_codes(self) -> list[str]:
        return list(self.candidate_sku_codes) if self.candidates_are_current else []


__all__ = ["ShoppingSessionState"]
