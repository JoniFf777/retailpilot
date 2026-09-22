"""Safe, user-observation-driven connection diagnosis."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .contracts import SourceRef


class DiagnosticCheck(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    check_id: str
    question: str
    safe_instruction: str
    source_ref: SourceRef
    expected_observations: list[str] = Field(default_factory=list, max_length=8)


class DiagnosticState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    round: int = Field(default=0, ge=0, le=5)
    answered_check_ids: list[str] = Field(default_factory=list, max_length=5)
    ruled_out: list[str] = Field(default_factory=list, max_length=16)
    observations: list[dict[str, str]] = Field(default_factory=list, max_length=32)


def record_observation(state: DiagnosticState, check_id: str, observation: str, source_ref: SourceRef) -> DiagnosticState:
    if check_id in state.answered_check_ids:
        raise ValueError("diagnostic_question_already_answered")
    if state.round >= 5:
        raise ValueError("diagnostic_round_limit")
    return state.model_copy(update={
        "round": state.round + 1,
        "answered_check_ids": [*state.answered_check_ids, check_id],
        "observations": [*state.observations, {"check_id": check_id, "observation": observation, "source": source_ref.source}],
    })


__all__ = ["DiagnosticCheck", "DiagnosticState", "record_observation"]
