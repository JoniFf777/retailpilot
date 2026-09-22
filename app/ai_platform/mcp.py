"""Server-owned, schema-validated read-only MCP discovery seam."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlsplit

from app.ai_platform.extensions import ExtensionDefinition, validate_mcp_tool
from app.runtime.contracts import (
    DatabaseAccess,
    ToolResourcePolicy,
    ToolSideEffectClass,
)
from app.runtime.tool_gateway import ToolCapability


@dataclass(frozen=True)
class McpServerConfig:
    name: str
    endpoint: str
    allowed_tool_ids: frozenset[str]
    enabled: bool = False

    def validate(self) -> None:
        parsed = urlsplit(self.endpoint)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("MCP server endpoints require query-free HTTPS.")
        if parsed.username or parsed.password:
            raise ValueError("MCP endpoints cannot contain credentials.")


class McpDiscovery:
    def __init__(
        self,
        config: McpServerConfig,
        fetch_tools: Callable[[str], list[dict[str, Any]]],
    ) -> None:
        self._config = config
        self._fetch_tools = fetch_tools

    def discover(self) -> tuple[ExtensionDefinition, ...]:
        if not self._config.enabled:
            return ()
        self._config.validate()
        definitions: list[ExtensionDefinition] = []
        for raw in self._fetch_tools(self._config.endpoint):
            name = str(raw.get("name") or "")
            description = str(raw.get("description") or "")
            schema = raw.get("input_schema", {})
            if not name or len(name) > 128 or len(description) > 4_096:
                raise ValueError("MCP tool definition exceeds bounds.")
            if not isinstance(schema, dict) or schema.get("type", "object") != "object":
                raise ValueError("MCP tool input schema must be a JSON object schema.")
            definition = ExtensionDefinition.model_validate(
                {
                    "extension_type": "mcp_tool",
                    "extension_key": name,
                    "version": 1,
                    "capability": raw.get("capability", "shopping"),
                    "content": description,
                    "side_effect": raw.get("side_effect", "read"),
                    "metadata": {"input_schema": schema},
                }
            )
            definitions.append(
                validate_mcp_tool(
                    definition,
                    allowed_tool_ids=set(self._config.allowed_tool_ids),
                )
            )
        return tuple(definitions)

    def capabilities(self) -> tuple[ToolCapability, ...]:
        """Convert discovered read-only tools into existing Gateway capabilities."""

        parsed = urlsplit(self._config.endpoint)
        host = (parsed.hostname or "").lower()
        return tuple(
            ToolCapability(
                name=definition.extension_key,
                allowed_agents=frozenset({"rag_agent"}),
                side_effect_class=ToolSideEffectClass.READ,
                requires_confirmation=False,
                resource_policy=ToolResourcePolicy(
                    database_access=DatabaseAccess.NONE,
                    network_access=True,
                    allowed_https_hosts=frozenset({host}),
                ),
            )
            for definition in self.discover()
        )


__all__ = ["McpDiscovery", "McpServerConfig"]
