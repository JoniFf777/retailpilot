"""Strict contracts shared by the task API, planner, worker and actions."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, field_validator, model_validator


TaskKind = Literal["bundle_selection", "compatibility_diagnosis", "after_sales_assessment"]
TaskStatus = Literal[
    "queued", "running", "waiting_input", "awaiting_approval", "succeeded",
    "failed", "cancelled", "expired",
]
StepStatus = Literal["pending", "running", "completed", "failed", "skipped", "superseded"]
Outcome = Literal[
    "recommended", "no_solution", "needs_information", "resolved", "unresolved",
    "eligible", "ineligible", "conditional", "unknown",
]
SourceKind = Literal["user_reported", "catalog", "order", "policy", "evidence", "derived"]
Role = Literal["coordinator", "catalog_analyst", "evidence_researcher", "reviewer"]
EvidenceStatus = Literal["ok", "degraded", "empty", "unavailable", "timeout", "disabled"]

MAX_PLAN_STEPS = 12
MAX_PARALLEL_STEPS = 3
MAX_PLAN_REPAIRS = 2
MAX_STEP_ATTEMPTS = 36
MAX_MODEL_ATTEMPTS = 24
MAX_INTERACTION_ROUNDS = 5
MAX_STEP_RETRIES = 2
MAX_ARTIFACT_BYTES = 512 * 1024
MAX_ARTIFACT_RESULT_BYTES = 64 * 1024
DEFAULT_TASK_TTL_HOURS = 24
DEFAULT_RESULT_RETENTION_DAYS = 7

CAPABILITIES: dict[Role, frozenset[str]] = {
    "coordinator": frozenset({"extract_goal", "verify_result", "compose_result"}),
    "catalog_analyst": frozenset({"catalog_candidates", "lookup_compatibility", "solve_bundle", "read_owned_order"}),
    "evidence_researcher": frozenset({"retrieve_evidence", "suggest_diagnostic_check", "assess_policy"}),
    "reviewer": frozenset({"verify_result"}),
}
READ_ONLY_CAPABILITIES = frozenset({
    "extract_goal", "catalog_candidates", "lookup_compatibility", "retrieve_evidence",
    "solve_bundle", "read_owned_order", "assess_policy", "suggest_diagnostic_check",
    "verify_result", "compose_result",
})
REQUIRED_VERIFY = "verify_result"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SourceRef(StrictModel):
    source: SourceKind
    source_id: StrictStr | None = None
    source_version: StrictStr | None = None
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    verified: StrictBool = False


class Fact(StrictModel):
    key: StrictStr
    value: Any
    source_ref: SourceRef


class ShoppingTaskRequest(StrictModel):
    schema_version: Literal["shopping-task-request.v1"] = "shopping-task-request.v1"
    kind: TaskKind
    goal_text: StrictStr = Field(min_length=1, max_length=4000)
    known_facts: list[Fact] = Field(default_factory=list, max_length=64)
    thread_id: StrictStr | None = Field(default=None, max_length=128)
    device_selector: StrictStr | None = Field(default=None, max_length=128)
    order_selector: StrictStr | None = Field(default=None, max_length=128)
    parent_task_id: UUID | None = None

    @model_validator(mode="after")
    def reject_control_fields(self) -> "ShoppingTaskRequest":
        # These names are intentionally not represented by this request model;
        # accepting them in a nested dict would let callers choose execution.
        forbidden = {"owner", "owner_id", "model", "endpoint", "mode", "tools", "role", "url"}
        keys = {fact.key.casefold() for fact in self.known_facts}
        if keys.intersection(forbidden):
            raise ValueError("control_fields_are_server_owned")
        return self


class GoalSpec(StrictModel):
    schema_version: Literal["goal-spec.v1"] = "goal-spec.v1"
    kind: TaskKind
    goal_text: StrictStr
    required_slots: list[StrictStr] = Field(default_factory=list, max_length=8)
    hard_constraints: dict[str, Any] = Field(default_factory=dict, max_length=32)
    soft_requirements: dict[str, Any] = Field(default_factory=dict, max_length=32)
    locked_selections: dict[str, StrictStr] = Field(default_factory=dict, max_length=8)
    excluded_skus: list[StrictStr] = Field(default_factory=list, max_length=32)
    open_questions: list[StrictStr] = Field(default_factory=list, max_length=16)
    facts: list[Fact] = Field(default_factory=list, max_length=64)
    diagnosis_state: dict[str, Any] = Field(default_factory=lambda: {"round": 0, "answered_check_ids": [], "ruled_out": [], "observations": []}, max_length=16)
    version: StrictInt = Field(default=1, ge=1)


class PlanStep(StrictModel):
    key: StrictStr = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_-]*$")
    capability: StrictStr
    role: Role
    depends_on: list[StrictStr] = Field(default_factory=list, max_length=12)
    input_refs: list[StrictStr] = Field(default_factory=list, max_length=16)
    output_kind: StrictStr = Field(min_length=1, max_length=64)
    read_only: StrictBool = True


class PlanProposal(StrictModel):
    schema_version: Literal["plan-proposal.v1"] = "plan-proposal.v1"
    revision: StrictInt = Field(default=1, ge=1)
    steps: list[PlanStep] = Field(min_length=1, max_length=MAX_PLAN_STEPS)
    mode: Literal["offline", "agent"] = "offline"
    reason: StrictStr = Field(default="deterministic_offline_plan", max_length=500)
    fingerprint: StrictStr = ""

    @model_validator(mode="after")
    def validate_fingerprint(self) -> "PlanProposal":
        payload = [step.model_dump(mode="json", exclude_none=True) for step in self.steps]
        expected = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if self.fingerprint and self.fingerprint != expected:
            raise ValueError("plan_fingerprint_mismatch")
        object.__setattr__(self, "fingerprint", expected)
        return self


class PlanRevision(StrictModel):
    schema_version: Literal["plan-revision.v1"] = "plan-revision.v1"
    revision: StrictInt = Field(ge=1)
    parent_revision: StrictInt | None = Field(default=None, ge=1)
    proposal: PlanProposal
    repair_reason: StrictStr | None = Field(default=None, max_length=500)
    invalidated_steps: list[StrictStr] = Field(default_factory=list, max_length=MAX_PLAN_STEPS)


class StepResult(StrictModel):
    schema_version: Literal["step-result.v1"] = "step-result.v1"
    task_id: UUID
    plan_revision: StrictInt = Field(ge=1)
    step_key: StrictStr
    role: Role
    status: Literal["completed", "failed", "waiting_input"]
    output_kind: StrictStr
    output: dict[str, Any] = Field(default_factory=dict)
    input_fingerprint: StrictStr = ""
    evidence_versions: list[StrictStr] = Field(default_factory=list, max_length=32)
    usage: dict[str, int | float | None] = Field(default_factory=dict, max_length=16)
    error_code: StrictStr | None = None


class VerificationIssue(StrictModel):
    code: StrictStr
    message: StrictStr
    affected_steps: list[StrictStr] = Field(default_factory=list, max_length=12)
    affected_artifacts: list[UUID] = Field(default_factory=list, max_length=12)
    affected_skus: list[StrictStr] = Field(default_factory=list, max_length=16)
    missing_facts: list[StrictStr] = Field(default_factory=list, max_length=16)
    allowed_repairs: list[StrictStr] = Field(default_factory=list, max_length=8)


class VerificationReport(StrictModel):
    schema_version: Literal["verification-report.v1"] = "verification-report.v1"
    status: Literal["pass", "repairable", "needs_input", "rejected"]
    issues: list[VerificationIssue] = Field(default_factory=list, max_length=32)
    rule_version: StrictStr = "shopping-rules.v1"
    reviewer_used: StrictBool = False
    progress_fingerprint: StrictStr | None = None


class Artifact(StrictModel):
    schema_version: Literal["shopping-artifact.v1"] = "shopping-artifact.v1"
    artifact_id: UUID | None = None
    kind: StrictStr
    task_id: UUID
    plan_revision: StrictInt = Field(ge=1)
    branch: StrictStr
    payload: dict[str, Any]
    input_fingerprint: StrictStr
    source_refs: list[SourceRef] = Field(default_factory=list, max_length=32)
    evidence_versions: list[StrictStr] = Field(default_factory=list, max_length=32)
    verification_status: Literal["pending", "passed", "failed", "superseded"] = "pending"


class ActionPreview(StrictModel):
    schema_version: Literal["action-preview.v1"] = "action-preview.v1"
    action_id: UUID | None = None
    action_type: Literal["add_bundle_to_cart", "save_after_sales_draft"]
    task_id: UUID
    goal_version: StrictInt = Field(ge=1)
    plan_revision: StrictInt = Field(ge=1)
    artifact_id: UUID
    action_version: StrictInt = Field(default=1, ge=1)
    expires_at: datetime
    payload: dict[str, Any]
    status: Literal["pending", "confirmed", "cancelled", "expired", "rejected"] = "pending"


class TaskStepView(StrictModel):
    key: StrictStr
    plan_revision: StrictInt = Field(ge=1)
    capability: StrictStr
    role: Role
    status: StepStatus
    attempt_count: StrictInt = Field(ge=0)
    output_artifact_id: UUID | None = None
    has_lease: StrictBool
    # A worker holds the fencing token, never the client; only presence and expiry
    # are ever exposed here (see repository.snapshot()).
    lease_until: datetime | None = None


class TaskArtifactView(StrictModel):
    id: UUID
    kind: StrictStr
    branch: StrictStr
    status: Literal["pending", "passed", "failed", "superseded"]
    payload: dict[str, Any]


class TaskBundleItemView(BaseModel):
    """Narrow view of `app.shopping_tasks.bundle.BundleItem`: only the fields
    TaskDetailPage.tsx reads. Kept independent rather than imported from `.bundle`
    to avoid a contracts <-> bundle <-> compatibility import cycle (compatibility.py
    imports SourceRef from this module); `extra="allow"` because the actual object
    has more fields (sku_id, name, currency, quantity, ...) than this view declares."""

    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)
    slot: StrictStr | None = None
    sku_code: StrictStr | None = None
    price: StrictStr | None = None


class TaskBundleOptionView(BaseModel):
    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)
    total: StrictStr | None = None
    currency: StrictStr | None = None
    items: list[TaskBundleItemView] = Field(default_factory=list)


class TaskBundleProposalView(BaseModel):
    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)
    options: list[TaskBundleOptionView] = Field(default_factory=list)


class TaskOutputView(BaseModel):
    """The task's composed output. Only the two fields the frontend renders today
    (`bundle_proposal`, `verification_report`) get real shape; `compose_result`'s
    payload also carries an `outcome` string plus kind-specific extras
    (`diagnostic_check` for compatibility_diagnosis, `assessment` for
    after_sales_assessment) that stay untyped and simply pass through, since which
    of those exist depends on `TaskSnapshot.kind`. `verification_report` reuses
    `VerificationReport` directly (not a narrowed view) since `verify_task_output()`
    below is its only producer, so the stored shape always matches exactly."""

    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)
    bundle_proposal: TaskBundleProposalView | None = None
    verification_report: VerificationReport | None = None


class TaskSnapshot(StrictModel):
    task_id: UUID
    owner_id: StrictStr
    kind: TaskKind
    status: TaskStatus
    mode: Literal["offline", "agent"]
    version: StrictInt
    goal: GoalSpec
    plan: PlanProposal | None = None
    steps: list[TaskStepView] = Field(default_factory=list)
    artifacts: list[TaskArtifactView] = Field(default_factory=list)
    output: TaskOutputView | None = None
    pending_interaction: dict[str, Any] | None = None
    last_sequence: StrictInt = 0


class TaskListItemView(StrictModel):
    task_id: StrictStr
    kind: TaskKind
    status: TaskStatus
    mode: Literal["offline", "agent"]
    version: StrictInt
    created_at: datetime


class TaskListResponse(StrictModel):
    items: list[TaskListItemView]
    limit: StrictInt
    offset: StrictInt


class TaskCreateResult(StrictModel):
    task_id: StrictStr
    status: TaskStatus
    version: StrictInt
    mode: Literal["offline", "agent"]
    accepted: StrictBool


class TaskCommandResult(StrictModel):
    """Shared response shape for the inputs/cancel/resume command endpoints."""

    task_id: StrictStr
    status: TaskStatus
    version: StrictInt


class TaskActionPreviewResult(StrictModel):
    action_id: StrictStr
    action_type: Literal["add_bundle_to_cart", "save_after_sales_draft"]
    status: StrictStr
    version: StrictInt
    expires_at: StrictStr
    payload: dict[str, Any]


class TaskActionResolution(StrictModel):
    schema_version: Literal["shopmind.task-action-resolution.v1"] = "shopmind.task-action-resolution.v1"
    task_id: StrictStr
    action_id: StrictStr
    action_version: StrictInt
    status: StrictStr
    side_effect: StrictBool | StrictStr
    cart_items: list[StrictStr] | None = None
    draft_only: StrictBool | None = None


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def canonical_fingerprint(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()


def money(value: Any) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))
