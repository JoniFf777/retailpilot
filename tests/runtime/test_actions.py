import pytest

from app.runtime.actions import (
    ACTION_REGISTRY,
    ActionDefinition,
    ActionRegistry,
    ActionRegistryError,
)
from app.runtime.contracts import (
    ActionRequest,
    ActionRiskClass,
    ActionTransitionRequest,
)


def test_add_to_cart_action_definition_selects_confirmation_tools() -> None:
    definition = ACTION_REGISTRY.validate_request(
        ActionRequest(action_type="add_to_cart", user_id="user-1")
    )

    assert definition.risk_class == ActionRiskClass.HIGH
    assert ACTION_REGISTRY.tool_for("add_to_cart", confirmed=True) == (
        "confirm_add_to_cart"
    )
    assert ACTION_REGISTRY.tool_for("add_to_cart", confirmed=False) == (
        "cancel_pending_action"
    )


def test_save_preference_uses_same_registered_confirmation_lifecycle() -> None:
    definition = ACTION_REGISTRY.validate_request(
        ActionRequest(
            action_type="save_preference",
            user_id="user-1",
            risk_class=ActionRiskClass.MEDIUM,
        )
    )

    assert definition.risk_class == ActionRiskClass.MEDIUM
    assert ACTION_REGISTRY.tool_for("save_preference", confirmed=True) == (
        "confirm_save_preference"
    )
    assert ACTION_REGISTRY.tool_for("save_preference", confirmed=False) == (
        "cancel_pending_action"
    )
    assert definition.edit_schema is not None


def test_action_registry_validates_exact_edit_schemas() -> None:
    assert ACTION_REGISTRY.validate_updated_arguments(
        "add_to_cart", {"quantity": 3}
    ) == {"quantity": 3}
    assert ACTION_REGISTRY.validate_updated_arguments(
        "save_preference",
        {"preference_type": "avoid", "preference_value": " glossy screens "},
    ) == {
        "preference_type": "avoid",
        "preference_value": "glossy screens",
    }

    for invalid in (
        {},
        {"quantity": 0},
        {"quantity": "2"},
        {"product_id": "OTHER"},
        {"quantity": 2, "risk_class": "low"},
    ):
        with pytest.raises(ActionRegistryError, match="edit payload is invalid"):
            ACTION_REGISTRY.validate_updated_arguments("add_to_cart", invalid)


def test_action_registry_rejects_edits_on_cancellation() -> None:
    request = ActionTransitionRequest(
        action_type="save_preference",
        action_id="pending-1",
        user_id="user-1",
        confirmed=False,
        updated_arguments={"preference_value": "new value"},
    )

    with pytest.raises(ActionRegistryError, match="only accepted with confirmation"):
        ACTION_REGISTRY.validate_transition(request)


def test_action_registry_rejects_unknown_and_mismatched_risk() -> None:
    registry = ActionRegistry(
        (
            ActionDefinition(
                action_type="export_data",
                risk_class=ActionRiskClass.MEDIUM,
                confirm_tool="confirm_export",
                cancel_tool="cancel_export",
            ),
        )
    )

    with pytest.raises(ActionRegistryError, match="not registered"):
        registry.definition_for("unknown")
    with pytest.raises(ActionRegistryError, match="invalid risk"):
        registry.validate_request(
            ActionRequest(
                action_type="export_data",
                user_id="user-1",
                risk_class=ActionRiskClass.HIGH,
            )
        )


def test_action_registry_validates_transition_identity_and_direction() -> None:
    request = ActionTransitionRequest(
        action_type="add_to_cart",
        action_id="pending-1",
        user_id="user-1",
        confirmed=True,
    )

    assert ACTION_REGISTRY.validate_transition(request).action_type == "add_to_cart"
    assert ACTION_REGISTRY.transition_tool(request) == "confirm_add_to_cart"

    with pytest.raises(ActionRegistryError, match="Action id is required"):
        ACTION_REGISTRY.validate_transition(request.model_copy(update={"action_id": " "}))


def test_action_registry_rejects_duplicate_registration() -> None:
    registry = ActionRegistry()
    definition = ActionDefinition(
        action_type="export_data",
        risk_class=ActionRiskClass.MEDIUM,
        confirm_tool="confirm_export",
        cancel_tool="cancel_export",
    )
    registry.register(definition)

    with pytest.raises(ActionRegistryError, match="already registered"):
        registry.register(definition)


def test_action_registry_rejects_duplicate_definitions_during_initialization() -> None:
    definition = ActionDefinition(
        action_type="export_data",
        risk_class=ActionRiskClass.MEDIUM,
        confirm_tool="confirm_export",
        cancel_tool="cancel_export",
    )

    with pytest.raises(ActionRegistryError, match="already registered"):
        ActionRegistry((definition, definition))
