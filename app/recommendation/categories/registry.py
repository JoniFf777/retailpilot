"""Server-owned registry for trusted category definition documents."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable

from app.recommendation.categories.models import (
    CategoryAttributeDefinition,
    CategoryDefinition,
    CategoryValidationIssue,
)


DEFAULT_DEFINITION_DIR = Path(__file__).resolve().parent
_WHITESPACE = re.compile(r"\s+")


def normalize_category_token(value: str) -> str:
    return _WHITESPACE.sub(" ", value.strip().casefold())


def alias_in_text(text: str, alias: str) -> bool:
    normalized_text = normalize_category_token(text)
    normalized_alias = normalize_category_token(alias)
    if normalized_alias.isascii() and normalized_alias.replace("_", "").replace("-", "").isalnum():
        return bool(re.search(rf"(?<![a-z0-9]){re.escape(normalized_alias)}(?![a-z0-9])", normalized_text))
    return normalized_alias in normalized_text


class CategoryRegistry:
    """Immutable, validated category definitions and lookup indexes."""

    def __init__(self, definitions: Iterable[CategoryDefinition]) -> None:
        ordered = tuple(sorted(definitions, key=lambda definition: definition.code))
        issues: list[CategoryValidationIssue] = []
        by_code: dict[str, CategoryDefinition] = {}
        aliases: dict[str, str] = {}
        for definition in ordered:
            if definition.code in by_code:
                issues.append(CategoryValidationIssue(code="duplicate_category_code", path=definition.code, detail=definition.code))
                continue
            by_code[definition.code] = definition
            for alias in (definition.code, definition.display_name, *definition.aliases):
                normalized = normalize_category_token(alias)
                existing = aliases.get(normalized)
                if existing is not None and existing != definition.code:
                    issues.append(CategoryValidationIssue(code="conflicting_category_alias", path=f"{definition.code}.aliases", detail=alias))
                else:
                    aliases[normalized] = definition.code
            for attribute in definition.attributes:
                if attribute.role == "hard" and not attribute.required:
                    # Hard attributes may be optional when the definition uses
                    # explicit request-time hard constraints. Catalogs still
                    # validate missing fields according to missing semantics.
                    continue
                if attribute.required and attribute.missing != "reject_if_hard":
                    issues.append(CategoryValidationIssue(code="invalid_required_missing_strategy", path=f"{definition.code}.{attribute.key}", detail=attribute.missing))
        if issues:
            ordered_issues = sorted(issues, key=lambda issue: (issue.code, issue.path, issue.detail))
            raise ValueError(
                "invalid CategoryRegistry: "
                + "; ".join(f"{issue.code}:{issue.detail}" for issue in ordered_issues)
            )
        self._definitions = by_code
        self._aliases = aliases

    @classmethod
    def from_directory(cls, directory: Path = DEFAULT_DEFINITION_DIR) -> "CategoryRegistry":
        path = Path(directory).resolve()
        if path != DEFAULT_DEFINITION_DIR and not path.is_dir():
            raise ValueError("category definition directory does not exist")
        definitions: list[CategoryDefinition] = []
        for file in sorted(path.glob("*.json"), key=lambda item: item.name):
            try:
                payload = json.loads(file.read_text(encoding="utf-8"))
                definitions.append(CategoryDefinition.model_validate(payload))
            except (OSError, json.JSONDecodeError, ValueError) as exc:
                raise ValueError(f"invalid category definition {file.name}: {exc}") from exc
        if not definitions:
            raise ValueError("CategoryRegistry has no definitions")
        return cls(definitions)

    def get(self, code: str) -> CategoryDefinition:
        try:
            return self._definitions[code]
        except KeyError as exc:
            raise KeyError(f"unsupported category: {code}") from exc

    def resolve_code_or_alias(self, value: str) -> str | None:
        return self._aliases.get(normalize_category_token(value))

    def supported_categories(self) -> tuple[CategoryDefinition, ...]:
        return tuple(self._definitions.values())

    def schema_for(self, code: str) -> CategoryDefinition:
        return self.get(code)

    def match_message(self, message: str) -> tuple[str, ...]:
        text = normalize_category_token(message)
        matches: set[str] = set()
        for alias, code in self._aliases.items():
            if len(alias) < 2:
                continue
            if alias_in_text(text, alias):
                matches.add(code)
        return tuple(sorted(matches))

    def match_attribute_categories(self, message: str) -> tuple[str, ...]:
        text = normalize_category_token(message)
        alias_owners: dict[str, set[str]] = {}
        for definition in self.supported_categories():
            for attribute in definition.attributes:
                for alias in (*attribute.aliases, *attribute.enum_aliases):
                    normalized = normalize_category_token(alias)
                    if len(normalized) >= 2:
                        alias_owners.setdefault(normalized, set()).add(definition.code)
        matches: set[str] = set()
        for definition in self.supported_categories():
            for attribute in definition.attributes:
                strong_aliases = [
                    normalize_category_token(alias)
                    for alias in (*attribute.aliases, *attribute.enum_aliases)
                    if len(normalize_category_token(alias)) >= 2
                    and len(alias_owners.get(normalize_category_token(alias), set())) == 1
                ]
                if any(alias_in_text(text, alias) for alias in strong_aliases):
                    matches.add(definition.code)
                    break
        return tuple(sorted(matches))

    def validate_request_attributes(self, code: str, attributes: dict[str, Any]) -> dict[str, Any]:
        definition = self.get(code)
        normalized: dict[str, Any] = {}
        for key, raw in attributes.items():
            attribute = definition.attribute_for(key)
            if attribute is None:
                raise ValueError(f"unknown category attribute: {key}")
            from app.recommendation.constraints import normalize_constraint

            normalized[key] = normalize_constraint(attribute, raw)
        return normalized

    def validate_catalog_attributes(
        self,
        code: str,
        attributes: dict[str, Any],
        *,
        path: str = "attributes",
    ) -> list[CategoryValidationIssue]:
        definition = self.get(code)
        issues: list[CategoryValidationIssue] = []
        declared = {attribute.canonical_catalog_key: attribute for attribute in definition.attributes}
        for key in sorted(attributes):
            if key not in declared:
                issues.append(CategoryValidationIssue(code="unknown_attribute", path=f"{path}.{key}", detail=code))
        from app.recommendation.constraints import validate_catalog_value

        for attribute in definition.attributes:
            catalog_key = attribute.canonical_catalog_key
            if catalog_key not in attributes:
                if attribute.required or attribute.missing == "reject_if_hard":
                    issues.append(CategoryValidationIssue(code="required_attribute_missing", path=f"{path}.{catalog_key}", detail=code))
                continue
            try:
                validate_catalog_value(attribute, attributes[catalog_key])
            except ValueError as exc:
                issues.append(CategoryValidationIssue(code="attribute_type_invalid", path=f"{path}.{catalog_key}", detail=str(exc)))
        return issues


_DEFAULT_REGISTRY: CategoryRegistry | None = None


def default_category_registry() -> CategoryRegistry:
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        _DEFAULT_REGISTRY = CategoryRegistry.from_directory()
    return _DEFAULT_REGISTRY
