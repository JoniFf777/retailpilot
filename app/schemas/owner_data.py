"""Public authenticated owner-data lifecycle schemas."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.governance import MAX_OWNER_RUN_INSPECTION_EVENTS


class OwnerDataInspectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, max_length=128)
    memory_limit: int = Field(default=50, ge=1, le=100)


class OwnerMemoryCorrectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, max_length=128)
    memory_id: str = Field(min_length=1, max_length=128)
    content: str = Field(min_length=1, max_length=4000)

    @field_validator("memory_id", "content")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Owner memory field must not be blank.")
        return normalized


class OwnerMemoryDeletionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, max_length=128)
    memory_id: str = Field(min_length=1, max_length=128)

    @field_validator("memory_id")
    @classmethod
    def normalize_memory_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Owner memory identifier must not be blank.")
        return normalized


class OwnerDataDeletionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, max_length=128)
    deletion_request_id: UUID
    confirmed: Literal[True]


class OwnerRunInspectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, max_length=128)
    run_id: str | None = Field(default=None, min_length=1, max_length=128)
    trace_id: str | None = Field(default=None, min_length=1, max_length=128)
    event_limit: int = Field(
        default=50,
        ge=1,
        le=MAX_OWNER_RUN_INSPECTION_EVENTS,
    )

    @field_validator("run_id", "trace_id")
    @classmethod
    def normalize_selector(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("Run inspection selector must not be blank.")
        return normalized

    @model_validator(mode="after")
    def validate_selector(self) -> "OwnerRunInspectRequest":
        if (self.run_id is None) == (self.trace_id is None):
            raise ValueError("Exactly one run or trace identifier is required.")
        return self


__all__ = [
    "OwnerDataDeletionRequest",
    "OwnerDataInspectRequest",
    "OwnerMemoryCorrectionRequest",
    "OwnerMemoryDeletionRequest",
    "OwnerRunInspectRequest",
]
