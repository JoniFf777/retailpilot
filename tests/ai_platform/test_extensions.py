import pytest

from app.ai_platform.extensions import (
    ExtensionDefinition,
    ExtensionRegistry,
    ExtensionSnapshot,
    validate_mcp_tool,
)


def test_extension_registry_publishes_immutable_shopping_snapshot():
    definition = ExtensionDefinition(
        extension_type="skill",
        extension_key="compatibility-guide",
        version=1,
        capability="compatibility",
        content="Explain compatibility without changing facts.",
    )
    registry = ExtensionRegistry()
    registry.publish(ExtensionSnapshot("v2", (definition,)))
    assert registry.enabled_for("skill")[0].extension_key == "compatibility-guide"


def test_mcp_write_tool_is_rejected():
    definition = ExtensionDefinition(
        extension_type="mcp_tool",
        extension_key="add_to_cart",
        version=1,
        capability="commerce_action",
        side_effect="read",
    )
    with pytest.raises(ValueError):
        validate_mcp_tool(definition, allowed_tool_ids={"other"})
