"""Explicit three-state compatibility facts; interface names are not proof."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .contracts import SourceRef


CompatibilityState = Literal["supported", "unsupported", "unknown"]


class CompatibilityRule(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    source_ref: SourceRef
    left_sku: str
    right_sku: str
    state: CompatibilityState
    reason: str = Field(max_length=500)
    rule_version: str = "compatibility.v1"


def compatibility_key(left_sku: str, right_sku: str) -> str:
    return "|".join(sorted((left_sku, right_sku)))


def resolve_compatibility(
    left_sku: str, right_sku: str, rules: list[CompatibilityRule]
) -> CompatibilityRule:
    key = compatibility_key(left_sku, right_sku)
    matches = [
        rule
        for rule in rules
        if compatibility_key(rule.left_sku, rule.right_sku) == key
    ]
    if not matches:
        return CompatibilityRule(
            source_ref=SourceRef(source="derived", source_id="compatibility-missing"),
            left_sku=left_sku,
            right_sku=right_sku,
            state="unknown",
            reason="缺少明确的视频输出或供电兼容事实，不能从 USB-C 外形推断。",
        )
    return sorted(matches, key=lambda rule: rule.rule_version)[-1]


__all__ = [
    "CompatibilityRule",
    "CompatibilityState",
    "compatibility_key",
    "resolve_compatibility",
]
