"""Trusted declarative recommendation category definitions and registry."""

from .models import (
    AttributeType,
    CategoryAttributeDefinition,
    CategoryDefinition,
    CategoryIntentCandidate,
    ConstraintRole,
    FilterOperator,
    MissingStrategy,
    RankingStrategy,
    StructuredRecommendationExtraction,
)
from .registry import CategoryRegistry, default_category_registry

__all__ = [
    "AttributeType",
    "CategoryAttributeDefinition",
    "CategoryDefinition",
    "CategoryIntentCandidate",
    "CategoryRegistry",
    "ConstraintRole",
    "FilterOperator",
    "MissingStrategy",
    "RankingStrategy",
    "StructuredRecommendationExtraction",
    "default_category_registry",
]
