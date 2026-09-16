"""Typed, non-executable recommendation category definitions."""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


AttributeType = Literal["number", "string", "enum", "boolean"]
FilterOperator = Literal["eq", "gte", "lte", "contains", "match", "enum_match"]
ConstraintRole = Literal["hard", "soft", "hard_or_soft", "display_only"]
RankingStrategy = Literal[
    "higher_is_better",
    "lower_is_better",
    "exact_match",
    "preference_match",
    "neutral",
]
MissingStrategy = Literal[
    "reject_if_hard",
    "neutral",
    "deterministic_penalty",
    "ignore",
]


class NumericBounds(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    minimum: Decimal
    maximum: Decimal

    @model_validator(mode="after")
    def validate_order(self) -> "NumericBounds":
        if self.minimum > self.maximum:
            raise ValueError("numeric bounds minimum must not exceed maximum")
        return self


class CategoryAttributeDefinition(BaseModel):
    """All category-specific semantics expressed as data."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    catalog_key: str | None = Field(default=None, min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=128)
    type: AttributeType
    unit: str | None = Field(default=None, max_length=32)
    aliases: tuple[str, ...] = ()
    enum_values: tuple[str, ...] = ()
    enum_aliases: dict[str, str] = Field(default_factory=dict)
    allowed_operators: tuple[FilterOperator, ...] = ("eq",)
    role: ConstraintRole = "display_only"
    ranking: RankingStrategy = "neutral"
    missing: MissingStrategy = "ignore"
    weight: Decimal = Field(default=Decimal("1"), gt=0, le=1000)
    bounds: NumericBounds | None = None
    missing_penalty: Decimal | None = Field(default=None, ge=0, le=1)
    default_operator: FilterOperator | None = None
    required: bool = False
    multi_valued: bool = False
    display_order: int = Field(default=0, ge=0, le=10000)
    comparable: bool = False
    format_hint: str | None = Field(default=None, max_length=32)

    @field_validator("aliases", "enum_values")
    @classmethod
    def normalize_unique_strings(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values)
        if any(not value for value in normalized):
            raise ValueError("aliases and enum values must not be empty")
        if len(set(normalized)) != len(normalized):
            raise ValueError("aliases and enum values must be unique")
        return normalized

    @field_validator("enum_aliases")
    @classmethod
    def normalize_enum_aliases(cls, values: dict[str, str]) -> dict[str, str]:
        return {key.strip(): value.strip() for key, value in values.items()}

    @model_validator(mode="after")
    def validate_semantics(self) -> "CategoryAttributeDefinition":
        operator_matrix: dict[str, set[str]] = {
            "number": {"eq", "gte", "lte"},
            "string": {"eq", "contains", "match"},
            "enum": {"eq", "gte", "lte", "enum_match"},
            "boolean": {"eq"},
        }
        invalid = set(self.allowed_operators) - operator_matrix[self.type]
        if invalid:
            raise ValueError(
                f"operators {sorted(invalid)} are invalid for attribute type {self.type}"
            )
        if self.default_operator and self.default_operator not in self.allowed_operators:
            raise ValueError("default_operator must be one of allowed_operators")
        if self.type == "number" and self.bounds is None and self.ranking in {
            "higher_is_better",
            "lower_is_better",
        }:
            # Snapshot bounds are valid only when the definition explicitly
            # permits them through the bounded generic default.
            pass
        if self.type == "enum":
            if not self.enum_values:
                raise ValueError("enum attributes require enum_values")
            unknown = set(self.enum_aliases.values()) - set(self.enum_values)
            if unknown:
                raise ValueError(f"enum aliases reference unknown values: {sorted(unknown)}")
        elif self.enum_values or self.enum_aliases:
            raise ValueError("enum values/aliases are only valid for enum attributes")
        if self.multi_valued and self.type != "enum":
            raise ValueError("only enum attributes may be multi_valued")
        if self.bounds is not None and self.type != "number":
            raise ValueError("numeric bounds require a number attribute")
        if self.missing == "deterministic_penalty" and self.missing_penalty is None:
            raise ValueError("deterministic_penalty requires missing_penalty")
        if self.role == "display_only" and self.ranking != "neutral":
            raise ValueError("display_only attributes must use neutral ranking")
        if self.required and self.missing != "reject_if_hard":
            raise ValueError("required attributes must use reject_if_hard missing semantics")
        return self

    @property
    def canonical_catalog_key(self) -> str:
        return self.catalog_key or self.key

    def canonicalize_enum(self, value: Any) -> str:
        text = str(value).strip().lower()
        for canonical in self.enum_values:
            if text == canonical.lower():
                return canonical
        for alias, canonical in self.enum_aliases.items():
            if text == alias.strip().lower():
                return canonical
        raise ValueError(f"invalid enum value for {self.key}")


class CategoryDefinition(BaseModel):
    """A complete category contract loaded from trusted JSON."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    display_name: str = Field(min_length=1, max_length=128)
    aliases: tuple[str, ...] = ()
    definition_version: str = Field(min_length=1, max_length=32)
    attributes: tuple[CategoryAttributeDefinition, ...] = ()
    display_fields: tuple[str, ...] = ()
    request_requires_any: tuple[str, ...] = ()
    clarification_question: str = "请补充明确的商品类别和选购条件。"

    @field_validator("aliases", "display_fields", "request_requires_any")
    @classmethod
    def validate_unique_values(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values)
        if any(not value for value in normalized):
            raise ValueError("definition values must not be empty")
        if len(set(normalized)) != len(normalized):
            raise ValueError("definition values must be unique")
        return normalized

    @model_validator(mode="after")
    def validate_references(self) -> "CategoryDefinition":
        keys = [attribute.key for attribute in self.attributes]
        if len(set(keys)) != len(keys):
            raise ValueError("category attribute keys must be unique")
        key_set = set(keys)
        missing_display = set(self.display_fields) - key_set
        if missing_display:
            raise ValueError(f"display_fields reference unknown attributes: {sorted(missing_display)}")
        missing_request = set(self.request_requires_any) - key_set
        if missing_request:
            raise ValueError(f"request_requires_any reference unknown attributes: {sorted(missing_request)}")
        if not self.display_fields:
            object.__setattr__(self, "display_fields", tuple(attribute.key for attribute in sorted(self.attributes, key=lambda item: (item.display_order, item.key))))
        return self

    def attribute_for(self, key: str) -> CategoryAttributeDefinition | None:
        return next((attribute for attribute in self.attributes if attribute.key == key), None)

    def attributes_for_catalog_key(self, catalog_key: str) -> tuple[CategoryAttributeDefinition, ...]:
        return tuple(
            attribute
            for attribute in self.attributes
            if attribute.canonical_catalog_key == catalog_key
        )


class CategoryValidationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    path: str
    detail: str


class CategoryIntentCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    confidence: Decimal = Field(ge=0, le=1)


class StructuredRecommendationExtraction(BaseModel):
    """Bounded untrusted extractor output; Catalog facts are not accepted here."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    category_candidates: tuple[CategoryIntentCandidate, ...] = ()
    attributes: dict[str, Any] = Field(default_factory=dict)
    budget_min: Decimal | None = Field(default=None, gt=0)
    budget_max: Decimal | None = Field(default=None, gt=0)
    budget_currency: str | None = None
    availability_required: bool = True

    @model_validator(mode="after")
    def validate_budget_range(self) -> "StructuredRecommendationExtraction":
        if self.budget_min is not None and self.budget_max is not None and self.budget_min > self.budget_max:
            raise ValueError("budget_min must not exceed budget_max")
        return self
