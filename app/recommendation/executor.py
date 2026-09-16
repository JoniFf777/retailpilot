"""Common typed executor for the structured recommendation specialist chain.

The graph still owns domain functions, but their execution now goes through a
validated task/result contract with dependency ordering, cancellation and
bounded stage budgets. This keeps the structured path observable in the same
shape as the runtime Agent plan without turning pure catalog functions into
LLM calls.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any, Callable, Mapping

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RecommendationTaskStep(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    step_id: str = Field(min_length=1)
    stage: str = Field(min_length=1)
    depends_on: list[str] = Field(default_factory=list)


class RecommendationTaskPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "shopmind.recommendation-task-plan.v1"
    plan_id: str = Field(min_length=1)
    steps: list[RecommendationTaskStep]
    max_steps: int = Field(default=8, ge=1, le=16)

    @model_validator(mode="after")
    def validate_graph(self) -> "RecommendationTaskPlan":
        ids = [step.step_id for step in self.steps]
        if len(ids) != len(set(ids)):
            raise ValueError("recommendation task step IDs must be unique")
        known = set(ids)
        for step in self.steps:
            if set(step.depends_on).difference(known):
                raise ValueError("recommendation task dependency is unknown")
        return self


class RecommendationTaskResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "shopmind.recommendation-task-result.v1"
    plan_id: str
    status: str
    stage_results: dict[str, dict[str, Any]] = Field(default_factory=dict)
    stage_events: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[dict[str, str]] = Field(default_factory=list)


@dataclass(frozen=True)
class RecommendationTaskExecution:
    state: dict[str, Any]
    result: RecommendationTaskResult


class StructuredRecommendationExecutor:
    """Execute one validated recommendation plan with bounded dependencies."""

    def execute(
        self,
        state: Mapping[str, Any],
        plan: RecommendationTaskPlan,
        handlers: Mapping[str, Callable[[dict[str, Any]], dict[str, Any]]],
        *,
        cancellation_check: Callable[[], bool] | None = None,
    ) -> RecommendationTaskExecution:
        current = dict(state)
        completed: set[str] = set()
        results: dict[str, dict[str, Any]] = {}
        events: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        remaining = list(plan.steps)
        while remaining:
            if len(completed) >= plan.max_steps:
                errors.append({"code": "recommendation.step_budget_exceeded", "stage": "plan"})
                break
            frontier = [step for step in remaining if set(step.depends_on).issubset(completed)]
            if not frontier:
                errors.append({"code": "recommendation.dependency_blocked", "stage": "plan"})
                break
            step = frontier[0]
            remaining.remove(step)
            if cancellation_check is not None and cancellation_check():
                errors.append({"code": "recommendation.cancelled", "stage": step.stage})
                break
            started = perf_counter()
            events.append({"stage": step.stage, "status": "started", "step_id": step.step_id})
            handler = handlers.get(step.stage)
            if handler is None:
                errors.append({"code": "recommendation.handler_missing", "stage": step.stage})
                break
            try:
                output = handler(current)
            except Exception as exc:
                errors.append({"code": "recommendation.stage_failed", "stage": step.stage})
                events.append({"stage": step.stage, "status": "failed", "step_id": step.step_id})
                break
            current.update(output)
            results[step.stage] = output
            completed.add(step.step_id)
            events.append(
                {
                    "stage": step.stage,
                    "status": "completed",
                    "step_id": step.step_id,
                    "duration_ms": max(0, int((perf_counter() - started) * 1000)),
                }
            )
        status = "completed" if len(completed) == len(plan.steps) else "failed"
        current["recommendation_task"] = RecommendationTaskResult(
            plan_id=plan.plan_id,
            status=status,
            stage_results=results,
            stage_events=events,
            errors=errors,
        ).model_dump(mode="json")
        return RecommendationTaskExecution(
            state=current,
            result=RecommendationTaskResult.model_validate(current["recommendation_task"]),
        )


__all__ = [
    "RecommendationTaskExecution",
    "RecommendationTaskPlan",
    "RecommendationTaskResult",
    "RecommendationTaskStep",
    "StructuredRecommendationExecutor",
]
