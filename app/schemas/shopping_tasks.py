"""Public API schemas for durable shopping tasks."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

from app.shopping_tasks.contracts import Fact, ShoppingTaskRequest


class ShoppingTaskCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: StrictStr | None = None
    kind: Literal["bundle_selection", "compatibility_diagnosis", "after_sales_assessment"]
    goal_text: StrictStr = Field(min_length=1, max_length=4000)
    known_facts: list[Fact] = Field(default_factory=list, max_length=64)
    thread_id: StrictStr | None = Field(default=None, max_length=128)
    device_selector: StrictStr | None = Field(default=None, max_length=128)
    order_selector: StrictStr | None = Field(default=None, max_length=128)
    parent_task_id: UUID | None = None

    def to_contract(self) -> ShoppingTaskRequest:
        return ShoppingTaskRequest.model_validate(self.model_dump(exclude={"user_id"}))


class ShoppingTaskInputRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: StrictStr | None = None
    expected_version: StrictInt = Field(ge=1)
    facts: list[Fact] = Field(default_factory=list, max_length=16)
    feedback: dict[str, Any] = Field(default_factory=dict, max_length=16)


class ShoppingTaskCommandRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: StrictStr | None = None
    expected_version: StrictInt = Field(ge=1)


class ShoppingTaskActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: StrictStr | None = None
    expected_version: StrictInt = Field(ge=1)
    action_type: Literal["add_bundle_to_cart", "save_after_sales_draft"]


class ShoppingTaskConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: StrictStr | None = None
    expected_version: StrictInt = Field(ge=1)
    confirmed: bool
