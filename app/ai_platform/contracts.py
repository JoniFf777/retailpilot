"""Transport-neutral contracts for ShopMind's business-scoped AI platform."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=True)


class CapabilityStatus(StrEnum):
    DISABLED = "disabled"
    READY = "ready"
    DEGRADED = "degraded"
    NOT_READY = "not_ready"


class EvidenceType(StrEnum):
    PRODUCT_GUIDE = "product_guide"
    COMPATIBILITY = "compatibility"
    BUYING_GUIDE = "buying_guide"
    STORE_POLICY = "store_policy"


class ModelOperation(StrEnum):
    ROUTER = "router"
    PLANNER = "planner"
    DECISION = "decision"
    QUERY_REWRITE = "query_rewrite"
    ANSWER_SYNTHESIS = "answer_synthesis"
    RERANK = "rerank"


class ModelFailureCode(StrEnum):
    UNAVAILABLE = "model_unavailable"
    CONNECTION = "model_connection_failure"
    FIRST_TOKEN_TIMEOUT = "model_first_token_timeout"
    TOTAL_TIMEOUT = "model_total_timeout"
    EMPTY_RESPONSE = "model_empty_response"
    PROTOCOL_ERROR = "model_protocol_error"
    BUDGET_EXCEEDED = "model_budget_exceeded"
    CIRCUIT_OPEN = "model_circuit_open"
    CANCELLED = "model_cancelled"


class PipelineNodeType(StrEnum):
    FETCHER = "fetcher"
    PARSER = "parser"
    CHUNKER = "chunker"
    ENRICHER = "enricher"
    INDEXER = "indexer"


class EvidenceScope(_Contract):
    product_ids: tuple[str, ...] = ()
    sku_codes: tuple[str, ...] = ()
    category_code: str | None = None
    compatibility_keys: tuple[str, ...] = ()
    policy_type: str | None = None
    region: str | None = None
    channel: str | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None

    @model_validator(mode="after")
    def validate_scope(self) -> "EvidenceScope":
        if self.valid_from and self.valid_until and self.valid_until <= self.valid_from:
            raise ValueError("Evidence validity window must be increasing.")
        for value in (*self.product_ids, *self.sku_codes, *self.compatibility_keys):
            if not value.strip():
                raise ValueError("Evidence scope identifiers cannot be blank.")
        return self


class ShoppingEvidenceDescriptor(_Contract):
    evidence_type: EvidenceType
    source_path: str = Field(min_length=1, max_length=1024)
    source_name: str | None = Field(default=None, max_length=255)
    source_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    content_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    scope: EvidenceScope
    title: str | None = Field(default=None, max_length=512)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_business_scope(self) -> "ShoppingEvidenceDescriptor":
        if self.evidence_type == EvidenceType.PRODUCT_GUIDE and not (
            self.scope.product_ids or self.scope.sku_codes or self.scope.category_code
        ):
            raise ValueError("Product guides require a product, SKU, or category scope.")
        if self.evidence_type == EvidenceType.BUYING_GUIDE and not self.scope.category_code:
            raise ValueError("Buying guides require a category scope.")
        if self.evidence_type == EvidenceType.STORE_POLICY and not self.scope.policy_type:
            raise ValueError("Store policies require a policy type.")
        if self.evidence_type == EvidenceType.COMPATIBILITY and not (
            self.scope.compatibility_keys
            or self.scope.product_ids
            or self.scope.category_code
        ):
            raise ValueError("Compatibility evidence requires a compatibility scope.")
        return self


class ModelCandidate(_Contract):
    candidate_id: str = Field(pattern=r"^[a-z][a-z0-9_.:-]{0,63}$")
    operation: ModelOperation
    provider: str = Field(min_length=1, max_length=64)
    model: str = Field(min_length=1, max_length=128)
    priority: int = Field(ge=1, le=1000)
    supports_streaming: bool = True
    supports_structured_output: bool = True
    first_token_timeout_ms: int = Field(default=10_000, ge=1, le=300_000)
    total_timeout_ms: int = Field(default=120_000, ge=1, le=900_000)
    max_attempts: int = Field(default=1, ge=1, le=3)
    cost_tier: str = Field(default="standard", min_length=1, max_length=32)


class ModelAttempt(_Contract):
    operation: ModelOperation
    candidate_id: str
    attempt: int = Field(ge=1, le=3)
    status: str = Field(pattern=r"^(started|succeeded|failed|skipped)$")
    failure_code: ModelFailureCode | None = None
    first_token_ms: int | None = Field(default=None, ge=0)
    duration_ms: int | None = Field(default=None, ge=0)
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    cost_usd: float | None = Field(default=None, ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ModelHealthSnapshot(_Contract):
    candidate_id: str
    operation: ModelOperation
    state: str = Field(pattern=r"^(closed|open|half_open)$")
    consecutive_failures: int = Field(ge=0)
    total_failures: int = Field(ge=0)
    total_successes: int = Field(ge=0)
    opened_until: datetime | None = None


class PipelineNodeResult(_Contract):
    node_type: PipelineNodeType
    status: str = Field(pattern=r"^(completed|failed|skipped)$")
    output_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    item_count: int = Field(default=0, ge=0)
    error_code: str | None = Field(default=None, max_length=64)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


__all__ = [
    "CapabilityStatus",
    "EvidenceScope",
    "EvidenceType",
    "ModelCandidate",
    "ModelFailureCode",
    "ModelHealthSnapshot",
    "ModelOperation",
    "ModelAttempt",
    "PipelineNodeResult",
    "PipelineNodeType",
    "ShoppingEvidenceDescriptor",
    "utc_now",
]
