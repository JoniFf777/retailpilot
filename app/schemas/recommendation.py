"""Stable Phase 1A recommendation contracts, independent from ChatResponse."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, field_validator, model_validator


Currency = str
SpecificationValueType = Literal["string", "integer", "decimal", "boolean", "string_list"]
RecommendationOutcome = Literal["recommended", "no_match", "clarification_required"]
CatalogSaleStatus = Literal["draft", "active", "inactive"]


def _currency(value: str) -> str:
    normalized = value.strip().upper()
    if value.strip() == chr(0xFFE5):
        return "CNY"
    aliases = {"元": "CNY", "人民币": "CNY", "RMB": "CNY", "¥": "CNY"}
    normalized = aliases.get(value.strip(), normalized)
    if len(normalized) != 3 or not normalized.isalpha():
        raise ValueError("currency must be a three-letter ISO 4217 code")
    return normalized


class Money(BaseModel):
    amount: StrictStr
    currency: StrictStr

    @field_validator("amount")
    @classmethod
    def normalize_amount(cls, value: str) -> str:
        try:
            amount = Decimal(value)
        except (InvalidOperation, ValueError) as exc:
            raise ValueError("amount must be a decimal string") from exc
        if not amount.is_finite():
            raise ValueError("amount must be finite")
        if amount <= 0:
            raise ValueError("amount must be greater than zero")
        if amount.as_tuple().exponent < -2:
            raise ValueError("amount cannot have more than two decimal places")
        return format(amount.quantize(Decimal("0.01")), ".2f")

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return _currency(value)


class LaptopConstraints(BaseModel):
    budget_max: Decimal | None = Field(default=None, gt=0)
    budget_currency: Currency | None = None
    memory_min_gb: int | None = Field(default=None, ge=1)
    storage_min_gb: int | None = Field(default=None, ge=1)
    weight_max_kg: Decimal | None = Field(default=None, gt=0)
    cpu_tier_min: str | None = None
    gpu_tier_min: str | None = None
    screen_inches: Decimal | None = Field(default=None, gt=0)
    primary_use_cases: list[str] = Field(default_factory=list)
    secondary_use_cases: list[str] = Field(default_factory=list)

    @field_validator("budget_currency")
    @classmethod
    def normalize_budget_currency(cls, value: str | None) -> str | None:
        return _currency(value) if value else None

    @model_validator(mode="after")
    def default_budget_currency(self) -> "LaptopConstraints":
        if self.budget_max is not None and self.budget_currency is None:
            self.budget_currency = "CNY"
        return self


class ProductSpecificationView(BaseModel):
    code: str
    name: str
    value_type: SpecificationValueType
    value: StrictStr | StrictInt | StrictBool | list[StrictStr]
    unit: str | None = None
    comparable: bool = False
    display_order: int = 0

    @model_validator(mode="after")
    def check_value_type(self) -> "ProductSpecificationView":
        expected = {
            "string": str,
            "integer": int,
            "decimal": str,
            "boolean": bool,
            "string_list": list,
        }[self.value_type]
        if self.value_type == "integer" and isinstance(self.value, bool):
            raise ValueError("integer specification cannot be boolean")
        if not isinstance(self.value, expected):
            raise ValueError("value does not match value_type")
        if self.value_type == "decimal":
            try:
                Decimal(self.value)
            except InvalidOperation as exc:
                raise ValueError("decimal specification must be a decimal string") from exc
        if self.value_type == "string_list" and not all(isinstance(item, str) for item in self.value):
            raise ValueError("string_list must contain strings")
        return self


class AvailabilityView(BaseModel):
    sale_status: CatalogSaleStatus
    available_quantity: int = Field(ge=0)
    in_stock: bool
    reason_code: str | None = None


class ScoreBreakdownItem(BaseModel):
    code: str
    name: str
    points: int = Field(ge=0)
    max_points: int = Field(ge=0)
    reason: str

    @model_validator(mode="after")
    def points_do_not_exceed_max(self) -> "ScoreBreakdownItem":
        if self.points > self.max_points:
            raise ValueError("points cannot exceed max_points")
        return self


class EvidenceView(BaseModel):
    source: str
    type: str
    field: str
    value: str
    ref: str | None = None


class AlternativeSkuView(BaseModel):
    sku_id: UUID
    sku_code: str
    sku_name: str
    money: Money
    differing_specifications: list[ProductSpecificationView] = Field(default_factory=list)
    availability: AvailabilityView


class Recommendation(BaseModel):
    product_id: UUID
    sku_id: UUID
    product_name: str
    sku_name: str
    money: Money
    specifications: list[ProductSpecificationView]
    score: int = Field(ge=0, le=100)
    score_breakdown: list[ScoreBreakdownItem]
    matched_hard_constraints: list[str] = Field(default_factory=list)
    matched_soft_preferences: list[str] = Field(default_factory=list)
    unmatched_soft_constraints: list[str] = Field(default_factory=list)
    soft_tradeoffs: list[str] = Field(default_factory=list)
    evidence: list[EvidenceView] = Field(default_factory=list)
    reason: str
    availability: AvailabilityView
    alternative_skus: list[AlternativeSkuView] = Field(default_factory=list)


class RecommendationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["shopmind.recommendation.v1"] = "shopmind.recommendation.v1"
    outcome: RecommendationOutcome
    ranking_policy_version: str
    request_summary: str
    structured_constraints: LaptopConstraints
    no_match_reason: str | None = None
    missing_fields: list[str] = Field(default_factory=list)
    clarification_question: str | None = None
    recommendations: list[Recommendation] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def validate_outcome(self) -> "RecommendationResult":
        if self.outcome == "recommended" and not self.recommendations:
            raise ValueError("recommended outcome needs at least one recommendation")
        if self.outcome == "no_match" and (self.recommendations or not self.no_match_reason):
            raise ValueError("no_match needs a reason and no recommendations")
        if self.outcome == "clarification_required" and (self.recommendations or not self.missing_fields or not self.clarification_question):
            raise ValueError("clarification_required needs fields, question, and no recommendations")
        return self
