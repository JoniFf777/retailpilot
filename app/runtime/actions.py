"""Typed registry for confirmation-first side effects."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .contracts import ActionRequest, ActionRiskClass, ActionTransitionRequest


class ActionRegistryError(ValueError):
    """Raised when an action is unknown or cannot enter the requested transition."""


class _ActionEdits(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @model_validator(mode="after")
    def require_at_least_one_edit(self) -> "_ActionEdits":
        if not self.model_fields_set or not self.model_dump(exclude_none=True):
            raise ValueError("At least one editable field is required.")
        return self


class AddToCartActionEdits(_ActionEdits):
    quantity: int | None = Field(default=None, gt=0, strict=True)


class SavePreferenceActionEdits(_ActionEdits):
    preference_type: Literal[
        "budget", "brand", "avoid", "usage", "style", "other"
    ] | None = None
    preference_value: str | None = Field(default=None, min_length=1)


@dataclass(frozen=True)
class ActionDefinition:
    action_type: str
    risk_class: ActionRiskClass
    confirm_tool: str
    cancel_tool: str
    requires_confirmation: bool = True
    edit_schema: type[BaseModel] | None = None


class ActionRegistry:
    """Small in-process registry that keeps sensitive action policy explicit."""

    def __init__(self, definitions: tuple[ActionDefinition, ...] = ()) -> None:
        self._definitions: dict[str, ActionDefinition] = {}
        for definition in definitions:
            self.register(definition)

    def register(self, definition: ActionDefinition) -> None:
        if not definition.action_type.strip():
            raise ActionRegistryError("Action type is required.")
        if definition.action_type in self._definitions:
            raise ActionRegistryError(
                f"Action '{definition.action_type}' is already registered."
            )
        self._definitions[definition.action_type] = definition

    def definition_for(self, action_type: str) -> ActionDefinition:
        try:
            return self._definitions[action_type]
        except KeyError as exc:
            raise ActionRegistryError(
                f"Action '{action_type}' is not registered."
            ) from exc

    def tool_for(self, action_type: str, *, confirmed: bool) -> str:
        definition = self.definition_for(action_type)
        if not definition.requires_confirmation:
            raise ActionRegistryError(
                f"Action '{action_type}' does not support confirmation transitions."
            )
        return definition.confirm_tool if confirmed else definition.cancel_tool

    def validate_request(self, request: ActionRequest) -> ActionDefinition:
        definition = self.definition_for(request.action_type)
        if request.risk_class != definition.risk_class:
            raise ActionRegistryError(
                f"Action '{request.action_type}' has an invalid risk class."
            )
        if not request.user_id.strip():
            raise ActionRegistryError("Action user_id is required.")
        return definition

    def validate_transition(
        self, request: ActionTransitionRequest
    ) -> ActionDefinition:
        definition = self.definition_for(request.action_type)
        if not request.action_id.strip():
            raise ActionRegistryError("Action id is required.")
        if not request.user_id.strip():
            raise ActionRegistryError("Action user_id is required.")
        if not definition.requires_confirmation:
            raise ActionRegistryError(
                f"Action '{request.action_type}' does not support confirmation transitions."
            )
        if request.updated_arguments is not None:
            if not request.confirmed:
                raise ActionRegistryError(
                    "Action edits are only accepted with confirmation."
                )
            self.validate_updated_arguments(
                request.action_type,
                request.updated_arguments,
            )
        return definition

    def validate_updated_arguments(
        self,
        action_type: str,
        updated_arguments: dict[str, Any],
    ) -> dict[str, Any]:
        definition = self.definition_for(action_type)
        if definition.edit_schema is None:
            raise ActionRegistryError(
                f"Action '{action_type}' does not support edits."
            )
        try:
            validated = definition.edit_schema.model_validate(updated_arguments)
        except ValidationError as exc:
            raise ActionRegistryError(
                f"Action '{action_type}' edit payload is invalid."
            ) from exc
        return validated.model_dump(exclude_none=True)

    def transition_tool(self, request: ActionTransitionRequest) -> str:
        self.validate_transition(request)
        return self.tool_for(request.action_type, confirmed=request.confirmed)


ACTION_REGISTRY = ActionRegistry(
    (
        ActionDefinition(
            action_type="add_to_cart",
            risk_class=ActionRiskClass.HIGH,
            confirm_tool="confirm_add_to_cart",
            cancel_tool="cancel_pending_action",
            edit_schema=AddToCartActionEdits,
        ),
        ActionDefinition(
            action_type="save_preference",
            risk_class=ActionRiskClass.MEDIUM,
            confirm_tool="confirm_save_preference",
            cancel_tool="cancel_pending_action",
            edit_schema=SavePreferenceActionEdits,
        ),
    )
)


__all__ = [
    "ACTION_REGISTRY",
    "AddToCartActionEdits",
    "ActionDefinition",
    "ActionRegistry",
    "ActionRegistryError",
    "SavePreferenceActionEdits",
]
