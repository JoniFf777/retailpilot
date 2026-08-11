"""Pure evidence projection; raw RAG payloads are not public contracts."""

from collections.abc import Iterable

from app.schemas.recommendation import EvidenceView


ALLOWED_EVIDENCE_FIELDS = frozenset({"source", "type", "field", "value", "ref"})


def sanitize_evidence(items: Iterable[dict[str, object]]) -> list[EvidenceView]:
    sanitized: list[EvidenceView] = []
    for item in items:
        projected = {key: item[key] for key in ALLOWED_EVIDENCE_FIELDS if key in item}
        if {"source", "type", "field", "value"}.issubset(projected):
            sanitized.append(EvidenceView.model_validate(projected))
    return sanitized
