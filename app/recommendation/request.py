"""Deterministic category resolution helpers for structured recommendations."""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.recommendation import RecommendationRequest


MonitorResolution = Literal["1080p", "1440p", "4k"]


class MonitorCategoryAttributes(BaseModel):
    """Typed Monitor-owned request attributes; not part of global constraints."""

    model_config = ConfigDict(extra="forbid")

    size_min_inches: Decimal | None = Field(default=None, gt=0)
    resolution_min: MonitorResolution | None = None
    refresh_rate_min_hz: int | None = Field(default=None, ge=30)
    panel_type: Literal["ips", "va", "oled"] | None = None
    use_case: Literal["office", "gaming", "design"] | None = None


_BUDGET = re.compile(
    r"(?:预算\s*)?(?:(\d+(?:\.\d+)?)\s*(?:CNY|RMB|人民币|元|￥|¥)|(?:CNY|RMB|人民币|元|￥|¥)\s*(\d+(?:\.\d+)?))",
    re.IGNORECASE,
)
_SIZE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:英寸|寸|inch|in|\")", re.IGNORECASE)
_REFRESH = re.compile(r"(?:刷新率|refresh\s*rate)?\s*(\d+)\s*hz", re.IGNORECASE)


def _budget(message: str) -> tuple[Decimal | None, str | None]:
    match = _BUDGET.search(message)
    if match is None:
        return None, None
    amount = match.group(1) or match.group(2)
    return Decimal(amount), "CNY"


def parse_monitor_attributes(message: str) -> MonitorCategoryAttributes:
    lowered = message.lower()
    values: dict[str, object] = {}
    size = _SIZE.search(message)
    if size is not None:
        values["size_min_inches"] = Decimal(size.group(1))
    if "4k" in lowered or "2160" in lowered:
        values["resolution_min"] = "4k"
    elif "2k" in lowered or "1440p" in lowered or "2560" in lowered:
        values["resolution_min"] = "1440p"
    elif "1080p" in lowered or "全高清" in message:
        values["resolution_min"] = "1080p"
    refresh = _REFRESH.search(message)
    if refresh is not None:
        values["refresh_rate_min_hz"] = int(refresh.group(1))
    for term, panel in (("oled", "oled"), ("ips", "ips"), ("va", "va")):
        if term in lowered:
            values["panel_type"] = panel
            break
    if any(term in message for term in ("游戏", "电竞", "gaming")) or "gaming" in lowered:
        values["use_case"] = "gaming"
    elif any(term in message for term in ("设计", "修图", "design")) or "design" in lowered:
        values["use_case"] = "design"
    elif any(term in message for term in ("办公", "office")) or "office" in lowered:
        values["use_case"] = "office"
    return MonitorCategoryAttributes.model_validate(values)


def parse_recommendation_request(message: str, category: str) -> RecommendationRequest:
    """Build a shared request after the gate has resolved category."""

    budget_max, budget_currency = _budget(message)
    if category == "monitor":
        attributes = parse_monitor_attributes(message)
        generic_preferences = [attributes.use_case] if attributes.use_case else []
        return RecommendationRequest(
            category="monitor",
            budget_max=budget_max,
            budget_currency=budget_currency,
            generic_preferences=generic_preferences,
            category_attributes=attributes.model_dump(exclude_none=True),
        )
    if category == "laptop":
        from app.recommendation.constraints import parse_laptop_constraints

        constraints = parse_laptop_constraints(message)
        return RecommendationRequest(
            category="laptop",
            budget_max=constraints.budget_max,
            budget_currency=constraints.budget_currency,
            generic_preferences=[
                *constraints.primary_use_cases,
                *constraints.secondary_use_cases,
            ],
            category_attributes=constraints.model_dump(
                exclude={"budget_max", "budget_currency"},
                exclude_none=True,
            ),
        )
    return RecommendationRequest(category="unknown")


__all__ = [
    "MonitorCategoryAttributes",
    "parse_monitor_attributes",
    "parse_recommendation_request",
]
