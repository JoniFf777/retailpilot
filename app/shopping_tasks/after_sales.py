"""Owner-order after-sales assessment without hidden policy defaults."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .contracts import SourceRef


class OrderFactEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    order_id: str
    owner_id: str
    order_status: str
    order_date: date | None = None
    delivered_at: date | None = None
    payment_status: str | None = None
    item_skus: list[str] = Field(default_factory=list, max_length=64)
    facts: list[SourceRef] = Field(default_factory=list, max_length=32)


class PolicyRule(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    policy_type: str
    region: str
    channel: str
    valid_from: date
    valid_until: date | None = None
    return_window_days: int | None = Field(default=None, ge=0, le=3650)
    requires_unopened: bool = False
    source_ref: SourceRef


class AfterSalesAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    outcome: Literal["eligible", "ineligible", "conditional", "unknown"]
    reason: str
    missing_facts: list[str] = Field(default_factory=list, max_length=16)
    system_facts: list[SourceRef] = Field(default_factory=list, max_length=32)
    user_claims: list[SourceRef] = Field(default_factory=list, max_length=32)
    policy_ref: SourceRef | None = None


def assess_after_sales(order: OrderFactEnvelope, policy: PolicyRule | None, *, today: date, user_claims: list[SourceRef] | None = None) -> AfterSalesAssessment:
    claims = user_claims or []
    if policy is None:
        return AfterSalesAssessment(outcome="unknown", reason="没有当前适用政策，不能使用隐藏默认期限。", missing_facts=["current_policy"], system_facts=order.facts, user_claims=claims)
    if policy.valid_from > today or policy.valid_until is not None and policy.valid_until <= today:
        return AfterSalesAssessment(outcome="unknown", reason="政策版本不在当前有效期内。", missing_facts=["current_policy"], system_facts=order.facts, user_claims=claims)
    if order.delivered_at is None:
        return AfterSalesAssessment(outcome="conditional", reason="缺少可信送达日期；用户补充只能作为 user_reported。", missing_facts=["delivered_at"], system_facts=order.facts, user_claims=claims, policy_ref=policy.source_ref)
    if policy.return_window_days is None:
        return AfterSalesAssessment(outcome="unknown", reason="当前政策没有合法期限字段。", missing_facts=["return_window_days"], system_facts=order.facts, user_claims=claims, policy_ref=policy.source_ref)
    age = (today - order.delivered_at).days
    if age < 0:
        return AfterSalesAssessment(outcome="unknown", reason="送达日期晚于当前日期，不能判定。", missing_facts=["valid_delivery_date"], system_facts=order.facts, user_claims=claims, policy_ref=policy.source_ref)
    outcome = "eligible" if age <= policy.return_window_days else "ineligible"
    return AfterSalesAssessment(outcome=outcome, reason=f"根据当前政策和可信送达事实，已送达 {age} 天。", system_facts=order.facts, user_claims=claims, policy_ref=policy.source_ref)


__all__ = ["AfterSalesAssessment", "OrderFactEnvelope", "PolicyRule", "assess_after_sales"]
