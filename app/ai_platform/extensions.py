"""Validated Prompt, Skill and MCP definitions for shopping agents."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


SHOPPING_CAPABILITIES = frozenset(
    {
        "shopping",
        "product_selection",
        "comparison",
        "compatibility",
        "store_policy",
        "commerce_action",
    }
)


class ExtensionDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    extension_type: str = Field(pattern=r"^(prompt|skill|mcp_tool)$")
    extension_key: str = Field(pattern=r"^[a-z][a-z0-9_.:-]{0,127}$")
    version: int = Field(ge=1, le=100_000)
    capability: str = Field(min_length=1, max_length=64)
    agent_names: tuple[str, ...] = ()
    enabled: bool = True
    content: str = Field(default="", max_length=100_000)
    tool_ids: tuple[str, ...] = ()
    side_effect: str = Field(
        default="none", pattern=r"^(none|read|write|sensitive_write)$"
    )
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_shopping_scope(self) -> "ExtensionDefinition":
        if self.capability not in SHOPPING_CAPABILITIES:
            raise ValueError("Extension capability is outside ShopMind scope.")
        if self.extension_type == "skill" and not self.content.strip():
            raise ValueError("Skills require bounded instructions.")
        if self.extension_type == "mcp_tool" and self.side_effect in {
            "write",
            "sensitive_write",
        }:
            raise ValueError("MCP business writers require an explicit Action mapping.")
        return self

    @property
    def content_fingerprint(self) -> str:
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ExtensionSnapshot:
    version: str
    definitions: tuple[ExtensionDefinition, ...]


class ExtensionRegistry:
    """Atomic in-process snapshot registry; persistence is supplied by the repository."""

    def __init__(self, snapshot: ExtensionSnapshot | None = None) -> None:
        self._snapshot = snapshot or ExtensionSnapshot("shopmind-extensions.v1", ())

    @property
    def snapshot(self) -> ExtensionSnapshot:
        return self._snapshot

    def publish(self, snapshot: ExtensionSnapshot) -> None:
        keys: set[tuple[str, str]] = set()
        for definition in snapshot.definitions:
            definition_key = (definition.extension_type, definition.extension_key)
            if definition_key in keys:
                raise ValueError("Extension keys must be unique per type.")
            keys.add(definition_key)
        self._snapshot = ExtensionSnapshot(
            snapshot.version, tuple(snapshot.definitions)
        )

    def enabled_for(self, extension_type: str) -> tuple[ExtensionDefinition, ...]:
        return tuple(
            definition
            for definition in self._snapshot.definitions
            if definition.enabled and definition.extension_type == extension_type
        )


def validate_mcp_tool(
    definition: ExtensionDefinition,
    *,
    allowed_tool_ids: set[str],
) -> ExtensionDefinition:
    if definition.extension_type != "mcp_tool":
        raise ValueError("MCP validator requires an MCP definition.")
    if definition.extension_key not in allowed_tool_ids:
        raise ValueError("MCP tool is not allowlisted.")
    if definition.side_effect != "read":
        raise ValueError(
            "Only read-only MCP tools are admitted by the first registry slice."
        )
    return definition


__all__ = [
    "ExtensionDefinition",
    "ExtensionRegistry",
    "ExtensionSnapshot",
    "SHOPPING_CAPABILITIES",
    "validate_mcp_tool",
]
