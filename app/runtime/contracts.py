"""Structured runtime contracts for ShopMind V4.x internal execution."""

from __future__ import annotations

import hashlib
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from enum import Enum
from threading import RLock
from typing import Any, Callable, Iterable, Iterator
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RunOperation(str, Enum):
    CHAT = "chat"
    CONFIRM_PENDING_ACTION = "confirm_pending_action"


class RunMode(str, Enum):
    SINGLE = "single"
    MULTI = "multi"


class RunStatus(str, Enum):
    STARTED = "started"
    COMPLETED = "completed"
    CONFIRMATION_REQUIRED = "confirmation_required"
    CANCELLED = "cancelled"
    FAILED = "failed"


class EventVisibility(str, Enum):
    CLIENT = "client"
    INTERNAL = "internal"
    AUDIT = "audit"


class ToolCallStatus(str, Enum):
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ToolSideEffectClass(str, Enum):
    NONE = "none"
    READ = "read"
    WRITE = "write"
    SENSITIVE_WRITE = "sensitive_write"


class DatabaseAccess(str, Enum):
    NONE = "none"
    READ = "read"
    WRITE = "write"


class ActionRiskClass(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ActionStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    FAILED = "failed"


class AgentTaskStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentTransportFailureCode(str, Enum):
    UNAVAILABLE = "agent.transport_unavailable"
    TIMEOUT = "agent.transport_timeout"
    PROTOCOL_ERROR = "agent.transport_protocol_error"


class AgentTaskRetryOwner(str, Enum):
    DISABLED = "disabled"
    PLAN_EXECUTOR = "plan_executor"


class AgentPlanExecutionMode(str, Enum):
    SEQUENTIAL = "sequential"
    BOUNDED_PARALLEL = "bounded_parallel"


class AgentPlanStatus(str, Enum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class AgentPlanStepStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


class AgentPlanAttemptLifecycle(str, Enum):
    """Stable suffixes for persisted and streamed plan-attempt events."""

    ATTEMPT_STARTED = "attempt.started"
    ATTEMPT_COMPLETED = "attempt.completed"
    ATTEMPT_FAILED = "attempt.failed"
    ATTEMPT_CANCELLED = "attempt.cancelled"
    RETRY_SCHEDULED = "retry.scheduled"
    RETRY_STARTED = "retry.started"
    RETRY_SUCCEEDED = "retry.succeeded"
    ATTEMPTS_EXHAUSTED = "attempt.exhausted"
    RETRY_NON_RETRIABLE = "retry.non_retriable"
    RETRY_BUDGET_BLOCKED = "retry.budget_blocked"
    RETRY_CANCELLED = "retry.cancelled"


class AgentPlanRetryReason(str, Enum):
    """Closed retry-decision reasons safe for audit and evaluation output."""

    TRANSPORT_RETRIABLE = "transport_retriable"
    TRANSPORT_NON_RETRIABLE = "transport_non_retriable"
    FAILURE_CODE_NOT_ALLOWLISTED = "failure_code_not_allowlisted"
    RETRY_POLICY_DISABLED = "retry_policy_disabled"
    ATTEMPTS_EXHAUSTED = "attempts_exhausted"
    SUCCESS_AFTER_RETRY = "success_after_retry"
    USAGE_BUDGET = "usage_budget"
    TIME_BUDGET = "time_budget"
    DELEGATION_BUDGET = "delegation_budget"
    CANCELLATION_BEFORE_RETRY = "cancellation_before_retry"


class EvidenceConflictType(str, Enum):
    PRODUCT_SCOPE_MISMATCH = "product_evidence_scope_mismatch"


class EvidenceResolutionAction(str, Enum):
    EXCLUDE_EVIDENCE_AND_REQUEST_CLARIFICATION = (
        "exclude_evidence_and_request_clarification"
    )


class MemoryKind(str, Enum):
    WORKING = "working"
    EPISODIC = "episodic"
    LONG_TERM = "long_term"
    OPERATIONAL = "operational"


class MemoryScope(str, Enum):
    THREAD = "thread"
    USER = "user"
    OPERATIONAL = "operational"


class ErrorSource(str, Enum):
    API = "api"
    VALIDATION = "validation"
    AGENT = "agent"
    TOOL = "tool"
    PERSISTENCE = "persistence"
    TIMEOUT = "timeout"
    CANCELLATION = "cancellation"
    UNKNOWN = "unknown"


class RuntimeModel(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)


def build_agent_task_idempotency_key(run_id: str, task_id: str) -> str:
    """Derive an opaque retry identity from trusted run and task identity."""

    payload = f"{run_id}\0{task_id}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class AgentTaskRetryPolicy(RuntimeModel):
    """Server-owned task replay invariants; execution remains disabled by default."""

    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=True)

    owner: AgentTaskRetryOwner = AgentTaskRetryOwner.DISABLED
    max_attempts: int = Field(default=1, ge=1, le=3)
    retryable_failure_codes: frozenset[AgentTransportFailureCode] = Field(
        default_factory=frozenset
    )
    preserve_task_identity: bool = True
    account_each_attempt: bool = True

    @model_validator(mode="after")
    def validate_retry_ownership(self) -> "AgentTaskRetryPolicy":
        if not self.preserve_task_identity or not self.account_each_attempt:
            raise ValueError(
                "Agent task retries must preserve identity and account every attempt."
            )
        if self.owner == AgentTaskRetryOwner.DISABLED:
            if self.max_attempts != 1 or self.retryable_failure_codes:
                raise ValueError(
                    "Disabled Agent task retries require one attempt and no codes."
                )
            return self
        if self.max_attempts < 2 or not self.retryable_failure_codes:
            raise ValueError(
                "Plan-owned Agent task retries require multiple attempts and codes."
            )
        return self


class ClientMetadata(RuntimeModel):
    client_name: str | None = None
    client_version: str | None = None
    user_agent: str | None = None
    ip_address: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RunBudget(RuntimeModel):
    deadline_at: datetime | None = None
    max_duration_ms: int | None = Field(default=None, ge=0)
    max_steps: int | None = None
    max_tool_calls: int | None = None
    max_prompt_tokens: int | None = None
    max_completion_tokens: int | None = None
    max_total_tokens: int | None = None
    max_cost_usd: float | None = None
    max_delegation_depth: int | None = Field(default=None, ge=0)
    max_child_tasks: int | None = Field(default=None, ge=0)


class RuntimePolicy(RuntimeModel):
    stream: bool = False
    allow_sensitive_tools: bool = False
    tool_policy_version: str = "v3-compat"
    event_schema_version: str = "v4.3"
    max_retries: int = 0
    agent_task_retry_policy: AgentTaskRetryPolicy = Field(
        default_factory=AgentTaskRetryPolicy
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolResourcePolicy(RuntimeModel):
    """Capability-owned resource limits for a single runtime tool."""

    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=True)

    database_access: DatabaseAccess = DatabaseAccess.NONE
    network_access: bool = False
    allowed_https_hosts: frozenset[str] = Field(default_factory=frozenset)

    @model_validator(mode="after")
    def validate_network_boundary(self) -> "ToolResourcePolicy":
        if self.network_access and not self.allowed_https_hosts:
            raise ValueError("Network-enabled tools require an HTTPS host allowlist.")
        if self.allowed_https_hosts and not self.network_access:
            raise ValueError("HTTPS host allowlists require network access.")
        for host in self.allowed_https_hosts:
            normalized = host.strip().lower()
            if (
                not normalized
                or normalized != host
                or "://" in normalized
                or any(character in normalized for character in "/?#@")
            ):
                raise ValueError("HTTPS allowlist entries must be bare lowercase hosts.")
        return self


class MemoryReference(RuntimeModel):
    ref_id: str
    ref_type: str
    scope: str
    thread_id: str | None = None
    message_id: str | None = None
    summary_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentTask(RuntimeModel):
    """Typed in-process or remote-ready delegation request."""

    task_id: str = Field(default_factory=lambda: str(uuid4()))
    parent_task_id: str | None = None
    run_id: str
    thread_id: str | None = None
    user_id: str | None = None
    sender: str
    recipient: str
    intent: str
    input_data: dict[str, Any] = Field(default_factory=dict)
    context_references: list[MemoryReference] = Field(default_factory=list)
    expected_output_schema: str = "v1"
    trace_id: str
    deadline_at: datetime | None = None
    idempotency_key: str | None = None
    budget: RunBudget = Field(default_factory=RunBudget)
    delegation_depth: int = Field(default=0, ge=0)
    retry_policy: AgentTaskRetryPolicy = Field(default_factory=AgentTaskRetryPolicy)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_delegation_identity(self) -> "AgentTask":
        if self.parent_task_id is None and self.delegation_depth != 0:
            raise ValueError("Root Agent tasks must have delegation_depth 0.")
        if self.parent_task_id is not None and self.delegation_depth == 0:
            raise ValueError("Child Agent tasks must have delegation_depth above 0.")
        if self.parent_task_id == self.task_id:
            raise ValueError("Agent tasks cannot be their own parent.")
        if self.retry_policy.owner == AgentTaskRetryOwner.PLAN_EXECUTOR:
            expected_key = build_agent_task_idempotency_key(
                self.run_id,
                self.task_id,
            )
            if self.idempotency_key != expected_key:
                raise ValueError(
                    "Retriable Agent tasks require the trusted task idempotency key."
                )
        return self


class AgentPlanStep(RuntimeModel):
    """One validated specialist step in an execution plan."""

    step_id: str = Field(min_length=1)
    recipient: str = Field(min_length=1)
    intent: str = Field(min_length=1)
    depends_on: list[str] = Field(default_factory=list)
    parallel_eligible: bool = False
    retry_policy: AgentTaskRetryPolicy = Field(default_factory=AgentTaskRetryPolicy)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentExecutionPlan(RuntimeModel):
    """Transport-neutral plan validated before specialist execution."""

    plan_id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str | None = None
    planner_type: str = "deterministic"
    execution_mode: AgentPlanExecutionMode = AgentPlanExecutionMode.SEQUENTIAL
    max_parallelism: int = Field(default=1, ge=1)
    steps: list[AgentPlanStep] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_plan_graph(self) -> "AgentExecutionPlan":
        if self.execution_mode == AgentPlanExecutionMode.SEQUENTIAL:
            if self.max_parallelism != 1:
                raise ValueError("Sequential Agent plans require max_parallelism 1.")

        step_ids = [step.step_id for step in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("Agent plan step_id values must be unique.")

        known_ids = set(step_ids)
        dependencies = {step.step_id: step.depends_on for step in self.steps}
        for step in self.steps:
            if len(step.depends_on) != len(set(step.depends_on)):
                raise ValueError("Agent plan dependencies must be unique per step.")
            unknown = set(step.depends_on).difference(known_ids)
            if unknown:
                raise ValueError("Agent plan dependencies must reference known steps.")

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(step_id: str) -> None:
            if step_id in visiting:
                raise ValueError("Agent plan dependencies must be acyclic.")
            if step_id in visited:
                return
            visiting.add(step_id)
            for dependency in dependencies[step_id]:
                visit(dependency)
            visiting.remove(step_id)
            visited.add(step_id)

        for step_id in step_ids:
            visit(step_id)
        return self


class RunError(RuntimeModel):
    code: str
    message: str
    source: ErrorSource
    retriable: bool = False
    event_sequence: int | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class ToolCallRecord(RuntimeModel):
    tool_call_id: str = Field(default_factory=lambda: str(uuid4()))
    tool_name: str
    caller: str
    capability: str | None = None
    argument_hash: str | None = None
    status: ToolCallStatus = ToolCallStatus.COMPLETED
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None
    duration_ms: int | None = None
    side_effect_class: ToolSideEffectClass = ToolSideEffectClass.READ
    requires_confirmation: bool = False
    resource_policy: ToolResourcePolicy = Field(default_factory=ToolResourcePolicy)
    result_metadata: dict[str, Any] = Field(default_factory=dict)
    audit_reference: str | None = None
    audit_sequence: int | None = Field(default=None, ge=1)


class ActionRequest(RuntimeModel):
    """Typed request for preparing or resuming a sensitive side effect."""

    action_type: str
    user_id: str
    thread_id: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    preview: str = ""
    risk_class: ActionRiskClass = ActionRiskClass.HIGH
    expires_at: datetime | None = None
    idempotency_key: str | None = None


class ActionTransitionRequest(RuntimeModel):
    """Typed approve/cancel request for an existing pending action."""

    action_type: str
    action_id: str
    user_id: str
    thread_id: str | None = None
    confirmed: bool
    updated_arguments: dict[str, Any] | None = None


class ActionRecord(RuntimeModel):
    """Normalized action state exposed by the runtime action boundary."""

    action_id: str
    action_type: str
    user_id: str
    thread_id: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    preview: str = ""
    risk_class: ActionRiskClass = ActionRiskClass.HIGH
    status: ActionStatus = ActionStatus.PENDING
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime | None = None


class AgentEvent(RuntimeModel):
    sequence: int
    event_type: str
    timestamp: datetime = Field(default_factory=utc_now)
    agent_name: str | None = None
    trace_id: str | None = None
    visibility: EventVisibility = EventVisibility.INTERNAL
    payload: dict[str, Any] = Field(default_factory=dict)
    tool_call_id: str | None = None


class RunUsage(RuntimeModel):
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    cost_usd: float | None = Field(default=None, ge=0)
    tool_call_count: int = Field(default=0, ge=0)
    step_count: int = Field(default=0, ge=0)


def aggregate_run_usage(usages: Iterable[RunUsage]) -> RunUsage:
    """Aggregate measured attempts without treating unavailable metrics as zero."""

    samples = list(usages)

    def complete_sum(field_name: str) -> int | float | None:
        values = [getattr(usage, field_name) for usage in samples]
        return (
            sum(values)
            if values and all(value is not None for value in values)
            else None
        )

    total_values = [
        usage.total_tokens
        if usage.total_tokens is not None
        else (
            usage.input_tokens + usage.output_tokens
            if usage.input_tokens is not None and usage.output_tokens is not None
            else None
        )
        for usage in samples
    ]
    return RunUsage(
        input_tokens=complete_sum("input_tokens"),
        output_tokens=complete_sum("output_tokens"),
        total_tokens=(
            sum(total_values)
            if total_values and all(value is not None for value in total_values)
            else None
        ),
        cost_usd=complete_sum("cost_usd"),
        tool_call_count=sum(usage.tool_call_count for usage in samples),
        step_count=sum(usage.step_count for usage in samples),
    )


class AgentResult(RuntimeModel):
    """Typed outcome returned by an in-process or future remote Agent."""

    task_id: str
    status: AgentTaskStatus
    output_data: dict[str, Any] = Field(default_factory=dict)
    evidence_references: list[MemoryReference] = Field(default_factory=list)
    usage: RunUsage = Field(default_factory=RunUsage)
    error: RunError | None = None
    child_trace_ids: list[str] = Field(default_factory=list)
    completed_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_failure_error(self) -> "AgentResult":
        if self.status == AgentTaskStatus.FAILED and self.error is None:
            raise ValueError("Failed Agent results require a structured error.")
        return self


class AgentPlanStepResult(RuntimeModel):
    """Normalized result for one planned specialist step."""

    step_id: str
    recipient: str
    status: AgentPlanStepStatus
    result: AgentResult | None = None
    error: RunError | None = None
    usage: RunUsage | None = None
    attempt_count: int = Field(default=0, ge=0, le=3)
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime = Field(default_factory=utc_now)
    duration_ms: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_result_shape(self) -> "AgentPlanStepResult":
        if self.status == AgentPlanStepStatus.COMPLETED and self.result is None:
            raise ValueError("Completed Agent plan steps require an Agent result.")
        if self.status != AgentPlanStepStatus.COMPLETED and self.error is None:
            raise ValueError("Non-completed Agent plan steps require an error.")
        return self


class AgentPlanAttemptEvent(RuntimeModel):
    """Typed payload for one plan-owned specialist-attempt lifecycle event."""

    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=True)

    lifecycle: AgentPlanAttemptLifecycle
    step_id: str = Field(min_length=1)
    recipient: str = Field(min_length=1)
    attempt: int = Field(ge=1, le=3)
    max_attempts: int = Field(ge=1, le=3)
    next_attempt: int | None = Field(default=None, ge=2, le=3)
    failure_code: AgentTransportFailureCode | None = None
    error_code: str | None = None
    retriable: bool | None = None
    reason: AgentPlanRetryReason | None = None
    budget_field: str | None = None
    budget_reason: str | None = None
    usage: RunUsage | None = None

    @model_validator(mode="after")
    def validate_attempt_identity(self) -> "AgentPlanAttemptEvent":
        if self.attempt > self.max_attempts:
            raise ValueError("Attempt cannot exceed the configured maximum.")
        if self.next_attempt is not None:
            if self.next_attempt != self.attempt + 1:
                raise ValueError("Retry events must identify the next attempt.")
            if self.next_attempt > self.max_attempts:
                raise ValueError("Retry cannot exceed the configured maximum.")
        return self


class AgentPlanResult(RuntimeModel):
    """Deterministically ordered fan-in result for an execution plan."""

    plan_id: str
    status: AgentPlanStatus
    step_results: list[AgentPlanStepResult] = Field(default_factory=list)
    output_data: dict[str, dict[str, Any]] = Field(default_factory=dict)
    evidence_references: list[MemoryReference] = Field(default_factory=list)
    usage: RunUsage = Field(default_factory=RunUsage)
    errors: list[RunError] = Field(default_factory=list)
    completed_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_step_identity(self) -> "AgentPlanResult":
        step_ids = [step.step_id for step in self.step_results]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("Agent plan results require unique step IDs.")
        return self


class EvidenceConflict(RuntimeModel):
    """Typed disagreement between selected entities and supporting evidence."""

    conflict_type: EvidenceConflictType
    product_ids: list[str] = Field(default_factory=list)
    evidence_product_ids: list[str] = Field(default_factory=list)
    evidence_reference_ids: list[str] = Field(default_factory=list)


class EvidenceResolution(RuntimeModel):
    """Fail-closed handling selected for one or more evidence conflicts."""

    action: EvidenceResolutionAction
    excluded_summaries: list[str] = Field(default_factory=list)
    requires_followup: bool = True
    followup_reason: str


class MemoryItem(RuntimeModel):
    memory_id: str
    kind: MemoryKind
    scope: MemoryScope
    content: str
    user_id: str | None = None
    thread_id: str | None = None
    priority: int = 0
    token_estimate: int = 0
    provenance: dict[str, Any] = Field(default_factory=dict)
    confidence: float | None = None
    created_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ContextSlice(RuntimeModel):
    items: list[MemoryItem] = Field(default_factory=list)
    rendered_text: str = ""
    token_budget: int | None = None
    estimated_tokens: int = 0
    omitted_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class RunRequest(RuntimeModel):
    operation: RunOperation
    user_id: str | None = None
    thread_id: str | None = None
    input_text: str | None = None
    input_data: dict[str, Any] = Field(default_factory=dict)
    mode: RunMode = RunMode.MULTI
    request_id: str = Field(default_factory=lambda: str(uuid4()))
    idempotency_key: str | None = None
    deadline_at: datetime | None = None
    policy: RuntimePolicy = Field(default_factory=RuntimePolicy)
    budget: RunBudget = Field(default_factory=RunBudget)
    include_debug: bool = False
    client: ClientMetadata = Field(default_factory=ClientMetadata)
    requested_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RunContext(RuntimeModel):
    _metadata_lock: Any = PrivateAttr(default_factory=RLock)
    _cancellation_check: Callable[[], bool] | None = PrivateAttr(default=None)
    _event_emitter: Callable[..., AgentEvent] | None = PrivateAttr(default=None)

    run_id: str = Field(default_factory=lambda: str(uuid4()))
    runtime_thread_id: str = Field(default_factory=lambda: str(uuid4()))
    trace_id: str = Field(default_factory=lambda: str(uuid4()))
    request: RunRequest
    policy: RuntimePolicy = Field(default_factory=RuntimePolicy)
    budget: RunBudget = Field(default_factory=RunBudget)
    memory_references: list[MemoryReference] = Field(default_factory=list)
    context_slice: ContextSlice | None = None
    parent_run_id: str | None = None
    started_at: datetime = Field(default_factory=utc_now)
    cancellation_requested: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def user_id(self) -> str | None:
        return self.request.user_id

    @property
    def client_thread_id(self) -> str | None:
        return self.request.thread_id

    @contextmanager
    def locked_metadata(self) -> Iterator[dict[str, Any]]:
        """Serialize compound metadata reads/writes without persisting the lock."""

        with self._metadata_lock:
            yield self.metadata

    def metadata_snapshot(self) -> dict[str, Any]:
        """Return a stable deep copy for graph output or persistence."""

        with self._metadata_lock:
            return deepcopy(self.metadata)

    def bind_cancellation_check(self, check: Callable[[], bool] | None) -> None:
        """Attach a local cooperative cancellation probe without serializing it."""

        self._cancellation_check = check

    def request_cancellation(self) -> None:
        """Mark cancellation so all local execution boundaries observe it."""

        with self._metadata_lock:
            self.cancellation_requested = True

    def refresh_cancellation(self) -> bool:
        """Poll the bound probe and return the latest cancellation state."""

        check = self._cancellation_check
        if check is not None and check():
            self.request_cancellation()
        with self._metadata_lock:
            return self.cancellation_requested

    def bind_event_emitter(
        self,
        emitter: Callable[..., AgentEvent] | None,
    ) -> None:
        """Attach the Harness-owned sequenced event boundary."""

        self._event_emitter = emitter

    def emit_event(
        self,
        event_type: str,
        *,
        visibility: EventVisibility = EventVisibility.INTERNAL,
        payload: dict[str, Any] | None = None,
        agent_name: str | None = None,
        tool_call_id: str | None = None,
    ) -> AgentEvent | None:
        """Emit through the Harness when present; standalone graphs remain valid."""

        emitter = self._event_emitter
        if emitter is None:
            return None
        return emitter(
            event_type=event_type,
            visibility=visibility,
            payload=payload or {},
            agent_name=agent_name,
            tool_call_id=tool_call_id,
        )


class RunResult(RuntimeModel):
    run_id: str
    runtime_thread_id: str
    trace_id: str
    request_id: str
    user_id: str | None = None
    client_thread_id: str | None = None
    status: RunStatus
    answer: str = ""
    output_data: dict[str, Any] = Field(default_factory=dict)
    tool_calls: list[str] = Field(default_factory=list)
    tool_call_records: list[ToolCallRecord] = Field(default_factory=list)
    pending_action_id: str | None = None
    events: list[AgentEvent] = Field(default_factory=list)
    usage: RunUsage = Field(default_factory=RunUsage)
    error: RunError | None = None
    debug: dict[str, Any] | None = None
    completed_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)
