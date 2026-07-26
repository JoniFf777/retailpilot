"""PII-free success evidence for scheduled runtime retention cleanup."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, field_validator


RUNTIME_CLEANUP_EVIDENCE_SCHEMA_VERSION = (
    "shopmind.runtime-cleanup-evidence.v1"
)


class RuntimeCleanupEvidence(BaseModel):
    """Minimal marker proving that one cleanup invocation committed."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["shopmind.runtime-cleanup-evidence.v1"] = (
        RUNTIME_CLEANUP_EVIDENCE_SCHEMA_VERSION
    )
    status: Literal["succeeded"] = "succeeded"
    completed_at: datetime

    @field_validator("completed_at")
    @classmethod
    def require_aware_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Cleanup evidence timestamp must be timezone-aware.")
        return value.astimezone(timezone.utc)


class RuntimeCleanupEvidenceError(RuntimeError):
    """Sanitized evidence I/O or validation failure."""

    def __init__(self) -> None:
        super().__init__("Runtime cleanup evidence is invalid or unavailable.")


def write_runtime_cleanup_evidence(
    path: str | Path,
    *,
    completed_at: datetime | None = None,
) -> RuntimeCleanupEvidence:
    """Atomically replace the configured marker after a committed cleanup."""

    evidence = RuntimeCleanupEvidence(
        completed_at=completed_at or datetime.now(timezone.utc)
    )
    target = Path(path)
    temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(
            evidence.model_dump_json(indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(target)
    except OSError as exc:
        raise RuntimeCleanupEvidenceError() from exc
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
    return evidence


def load_runtime_cleanup_evidence(
    path: str | Path,
) -> RuntimeCleanupEvidence | None:
    """Load a marker without exposing its path or validation error."""

    try:
        payload = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise RuntimeCleanupEvidenceError() from exc
    try:
        return RuntimeCleanupEvidence.model_validate_json(payload)
    except Exception as exc:
        raise RuntimeCleanupEvidenceError() from exc


__all__ = [
    "RUNTIME_CLEANUP_EVIDENCE_SCHEMA_VERSION",
    "RuntimeCleanupEvidence",
    "RuntimeCleanupEvidenceError",
    "load_runtime_cleanup_evidence",
    "write_runtime_cleanup_evidence",
]
