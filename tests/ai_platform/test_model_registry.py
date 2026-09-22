import pytest

from app.ai_platform.contracts import ModelCandidate, ModelOperation
from app.ai_platform.model_registry import (
    ModelCandidateRegistry,
    ModelRegistrySnapshot,
    default_model_registry,
)


def make_candidate(identifier: str) -> ModelCandidate:
    return ModelCandidate(
        candidate_id=identifier,
        operation=ModelOperation.PLANNER,
        provider="test",
        model="test",
        priority=1,
    )


def test_registry_rejects_duplicate_ids_and_publishes_snapshot():
    with pytest.raises(ValueError):
        ModelCandidateRegistry(ModelRegistrySnapshot("v1", (make_candidate("same"), make_candidate("same"))))
    registry = default_model_registry()
    original = registry.snapshot.version
    registry.publish(ModelRegistrySnapshot("v2", registry.snapshot.candidates))
    assert original == "shopmind-models.v1"
    assert registry.snapshot.version == "v2"
