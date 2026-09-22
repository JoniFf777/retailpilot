from datetime import datetime, timedelta, timezone
from hashlib import sha256

import pytest
from pydantic import ValidationError

from app.ai_platform.contracts import (
    EvidenceScope,
    EvidenceType,
    ModelCandidate,
    ModelOperation,
    ShoppingEvidenceDescriptor,
)


def digest(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def test_shopping_evidence_descriptor_requires_business_scope() -> None:
    with pytest.raises(ValidationError):
        ShoppingEvidenceDescriptor(
            evidence_type=EvidenceType.BUYING_GUIDE,
            source_path="guide.md",
            source_fingerprint=digest("source"),
            content_fingerprint=digest("content"),
            scope=EvidenceScope(),
        )


def test_policy_scope_accepts_effective_window() -> None:
    start = datetime.now(timezone.utc)
    descriptor = ShoppingEvidenceDescriptor(
        evidence_type=EvidenceType.STORE_POLICY,
        source_path="return.md",
        source_fingerprint=digest("source"),
        content_fingerprint=digest("content"),
        scope=EvidenceScope(
            policy_type="return",
            valid_from=start,
            valid_until=start + timedelta(days=30),
        ),
    )
    assert descriptor.scope.policy_type == "return"


def test_model_candidate_is_server_owned_and_bounded() -> None:
    candidate = ModelCandidate(
        candidate_id="planner-primary",
        operation=ModelOperation.PLANNER,
        provider="local",
        model="deterministic",
        priority=1,
        max_attempts=2,
    )
    assert candidate.max_attempts == 2
