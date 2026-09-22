"""Server-owned model candidate registry for ShopMind operations."""

from __future__ import annotations

from dataclasses import dataclass

from app.ai_platform.contracts import ModelCandidate, ModelOperation
from app.ai_platform.resilience import ModelGateway


@dataclass(frozen=True)
class ModelRegistrySnapshot:
    version: str
    candidates: tuple[ModelCandidate, ...]

    def for_operation(self, operation: ModelOperation) -> tuple[ModelCandidate, ...]:
        return tuple(item for item in self.candidates if item.operation == operation)


class ModelCandidateRegistry:
    """Validate and atomically replace a model candidate snapshot."""

    def __init__(self, snapshot: ModelRegistrySnapshot) -> None:
        self._snapshot = self._validate(snapshot)

    @staticmethod
    def _validate(snapshot: ModelRegistrySnapshot) -> ModelRegistrySnapshot:
        if not snapshot.version.strip():
            raise ValueError("Model registry version is required.")
        ids = [item.candidate_id for item in snapshot.candidates]
        if len(ids) != len(set(ids)):
            raise ValueError("Model candidate IDs must be unique.")
        operations = set(item.operation for item in snapshot.candidates)
        if not operations:
            raise ValueError("Model registry cannot be empty.")
        return ModelRegistrySnapshot(snapshot.version, tuple(snapshot.candidates))

    @property
    def snapshot(self) -> ModelRegistrySnapshot:
        return self._snapshot

    def publish(self, snapshot: ModelRegistrySnapshot) -> None:
        self._snapshot = self._validate(snapshot)

    def gateway(self, **kwargs) -> ModelGateway:
        return ModelGateway(list(self._snapshot.candidates), **kwargs)


def default_model_registry(settings=None) -> ModelCandidateRegistry:
    """Build a safe development registry without reading client input."""

    candidates = []
    for index, operation in enumerate(ModelOperation, start=1):
        candidates.append(
            ModelCandidate(
                candidate_id=f"{operation.value}-default",
                operation=operation,
                provider="configured",
                model=str(getattr(settings, "workshop_model", "deterministic")),
                priority=index,
                supports_streaming=operation != ModelOperation.RERANK,
            )
        )
    return ModelCandidateRegistry(ModelRegistrySnapshot("shopmind-models.v1", tuple(candidates)))


__all__ = [
    "ModelCandidateRegistry",
    "ModelRegistrySnapshot",
    "default_model_registry",
]
