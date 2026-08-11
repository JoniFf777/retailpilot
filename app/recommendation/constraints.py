"""Small deterministic parser for the Phase 1A Laptop constraint vocabulary."""

from __future__ import annotations

import re
from decimal import Decimal

from app.schemas.recommendation import LaptopConstraints


_AMOUNT_AFTER_CURRENCY = re.compile(r"(?:预算\s*)?(?:JPY|CNY|RMB|人民币|元|￥|¥)\s*(\d+(?:\.\d+)?)", re.IGNORECASE)
_AMOUNT_BEFORE_CURRENCY = re.compile(r"(?:预算\s*)?(\d+(?:\.\d+)?)\s*(JPY|CNY|RMB|人民币|元|￥|¥)", re.IGNORECASE)
_MEMORY = re.compile(r"内存\s*(?:至少|不低于|不少于|>=)?\s*(\d+)\s*GB", re.IGNORECASE)


def parse_laptop_constraints(message: str) -> LaptopConstraints:
    """Parse only the closed Phase 1A Chinese/English demo vocabulary.

    Vague phrases such as ``尽量轻`` deliberately do not become a fabricated
    numeric hard constraint; a future extractor may turn them into a declared
    soft preference without changing this deterministic baseline.
    """
    text = message.strip()
    values: dict[str, object] = {}
    match = _AMOUNT_BEFORE_CURRENCY.search(text)
    if match is None:
        match = _AMOUNT_AFTER_CURRENCY.search(text)
        if match is not None:
            currency_match = re.search(r"JPY|CNY|RMB|人民币|元|￥|¥", match.group(0), re.IGNORECASE)
            values["budget_currency"] = currency_match.group(0) if currency_match else None
            values["budget_max"] = Decimal(match.group(1))
    else:
        values["budget_max"] = Decimal(match.group(1))
        values["budget_currency"] = match.group(2)
    memory = _MEMORY.search(text)
    if memory is not None:
        values["memory_min_gb"] = int(memory.group(1))
    primary: list[str] = []
    secondary: list[str] = []
    lowered = text.lower()
    if "java" in lowered:
        primary.append("java_development")
    if "剪视频" in text or "video" in lowered:
        secondary.append("video_editing")
    values["primary_use_cases"] = primary
    values["secondary_use_cases"] = secondary
    return LaptopConstraints.model_validate(values)
