"""Additive task-only category registry; released recommendation registry is untouched."""

from __future__ import annotations

import json
from pathlib import Path

from app.recommendation.categories import CategoryDefinition, CategoryRegistry, default_category_registry


_DOCK_PATH = Path(__file__).with_name("dock_category.json")
_TASK_REGISTRY: CategoryRegistry | None = None


def default_task_category_registry() -> CategoryRegistry:
    global _TASK_REGISTRY
    if _TASK_REGISTRY is None:
        dock = CategoryDefinition.model_validate(json.loads(_DOCK_PATH.read_text(encoding="utf-8")))
        _TASK_REGISTRY = CategoryRegistry([*default_category_registry().supported_categories(), dock])
    return _TASK_REGISTRY


__all__ = ["default_task_category_registry"]
