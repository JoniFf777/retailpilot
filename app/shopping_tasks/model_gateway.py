"""Real structured task planning through the existing Gateway and Harness.

The adapter is lazy and opt-in. Offline mode never imports or invokes a model.
Agent mode uses the server-owned candidate registry, emits Gateway attempts into
the existing Harness event stream, and falls back to the deterministic plan on
provider/configuration/protocol failure.
"""

from __future__ import annotations

from hashlib import sha256
import json
from threading import Lock
from time import perf_counter
from typing import Any

from langchain.chat_models import init_chat_model

from app.ai_platform.contracts import ModelOperation
from app.ai_platform.model_registry import default_model_registry
from app.ai_platform.resilience import ModelGateway, ModelInvocation, SharedAIBudget
from app.runtime import RunMode, RunOperation, RunRequest, ShopMindRuntimeHarness, build_runtime_budget, build_runtime_policy

from .contracts import GoalSpec, PlanProposal, PlanStep, VerificationIssue, VerificationReport
from .planner import assert_valid_plan, offline_plan


_GATEWAY_LOCK = Lock()
_GATEWAY_BY_MODEL: dict[str, ModelGateway] = {}


def _gateway(settings: Any, runtime_context: Any | None = None) -> ModelGateway:
    model_name = str(getattr(settings, "workshop_model", ""))
    with _GATEWAY_LOCK:
        gateway = _GATEWAY_BY_MODEL.get(model_name)
        if gateway is None:
            registry = default_model_registry(settings)
            candidates = [
                candidate.model_copy(
                    update={
                        # Task planning/review is asynchronous and the current
                        # reasoning model has a measured long tail near 120s.
                        # The worker renews its lease while this bounded call is
                        # in flight, so use a truthful task-specific deadline.
                        "total_timeout_ms": 180_000,
                    }
                )
                for candidate in registry.snapshot.candidates
            ]
            gateway = ModelGateway(
                candidates,
                budget=SharedAIBudget(max_total_tokens=60_000),
            )
            _GATEWAY_BY_MODEL[model_name] = gateway
    if runtime_context is not None:
        from app.ai_platform.model_adapter import harness_attempt_observer

        gateway.set_attempt_observer(harness_attempt_observer(runtime_context))
    return gateway


def _prompt(goal: GoalSpec, baseline: PlanProposal) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You are the ShopMind coordinator. Return only one JSON object. "
                "Use the supplied baseline as a safe capability DAG: you may keep it "
                "or revise dependencies, but must preserve the task kind, use only "
                "the supplied read-only capabilities, and include verify_result. "
                "Never add URLs, owners, models, tools, payments, or writes. "
                "Required shape: {schema_version:'plan-proposal.v1', revision:1, "
                "steps:[{key,capability,role,depends_on,input_refs,output_kind,read_only:true}], "
                "mode:'agent', reason:'short reason', fingerprint:''}."
            ),
        },
        {
            "role": "user",
            "content": json.dumps({"goal": goal.model_dump(mode="json"), "baseline": baseline.model_dump(mode="json")}, ensure_ascii=False, sort_keys=True),
        },
    ]


def _invoke_structured(candidate, goal: GoalSpec, baseline: PlanProposal) -> PlanProposal:
    started = perf_counter()
    llm = _chat_model(candidate, max_tokens=2500)
    proposal = _json_response(llm.invoke(_prompt(goal, baseline)))
    result = _coerce_plan_response(proposal, baseline=baseline, goal=goal)
    # Keep the latency calculation local for future ModelInvocation accounting;
    # providers that expose token usage are still allowed to populate it.
    _ = int((perf_counter() - started) * 1000)
    return result


def _coerce_plan_response(
    payload: dict[str, Any],
    *,
    baseline: PlanProposal,
    goal: GoalSpec,
) -> PlanProposal:
    """Project a model proposal onto the server-owned capability contract."""

    baseline_by_key = {step.key: step for step in baseline.steps}
    raw_steps = payload.get("steps")
    if not isinstance(raw_steps, list):
        raw_steps = []
    proposed: list[PlanStep] = []
    seen: set[str] = set()
    for raw in raw_steps:
        if not isinstance(raw, dict):
            continue
        key = str(raw.get("key") or "")
        source = baseline_by_key.get(key)
        if source is None or key in seen:
            continue
        seen.add(key)
        dependencies = raw.get("depends_on")
        input_refs = raw.get("input_refs")
        proposed.append(
            source.model_copy(
                update={
                    "depends_on": (
                        [str(item) for item in dependencies]
                        if isinstance(dependencies, list)
                        else source.depends_on
                    ),
                    "input_refs": (
                        [str(item) for item in input_refs]
                        if isinstance(input_refs, list)
                        else source.input_refs
                    ),
                }
            )
        )
    proposed.extend(step for step in baseline.steps if step.key not in seen)
    result = PlanProposal(
        revision=1,
        steps=proposed,
        mode="agent",
        reason="structured_gateway_plan",
    )
    try:
        assert_valid_plan(result, goal=goal)
    except ValueError:
        result = baseline.model_copy(
            update={"mode": "agent", "reason": "structured_gateway_plan:policy_normalized"}
        )
    return result


def plan_with_gateway(
    goal: GoalSpec,
    *,
    settings: Any,
    owner_id: str,
    runtime_context: Any | None = None,
) -> PlanProposal:
    baseline = offline_plan(goal)
    gateway = _gateway(settings, runtime_context)

    def executor(context):
        del context
        invocation = gateway.execute(
            ModelOperation.PLANNER,
            lambda candidate: ModelInvocation(value=_invoke_structured(candidate, goal, baseline)),
        )
        return {"task_planner": invocation.value.model_dump(mode="json")}

    request = RunRequest(
        operation=RunOperation.CHAT,
        user_id=owner_id,
        input_text=goal.goal_text,
        mode=RunMode.MULTI,
        idempotency_key=f"shopping-plan:{sha256(json.dumps(goal.model_dump(mode='json'), sort_keys=True).encode()).hexdigest()}",
        policy=build_runtime_policy(settings, RunOperation.CHAT),
        budget=build_runtime_budget(settings),
        metadata={"shopping_task_planner": True, "planner_mode": "agent"},
    )
    try:
        result = ShopMindRuntimeHarness().run(request, executor, raise_on_error=False)
        if result.error is None and isinstance(result.output_data.get("task_planner"), dict):
            return PlanProposal.model_validate(result.output_data["task_planner"])
        if result.error is not None:
            reason = f"gateway_error:{getattr(result.error, 'code', 'unknown')}"
        else:
            reason = "gateway_error:invalid_harness_output"
    except Exception as exc:
        reason = type(exc).__name__
    return baseline.model_copy(update={"mode": "agent", "reason": f"agent_fallback:{reason}"})


def _review_prompt(
    goal: GoalSpec,
    rules: VerificationReport,
    task_output: dict[str, Any],
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You are the ShopMind result reviewer. Return only one JSON object "
                "as a VerificationReport supplement. You may identify missing explanation, "
                "unsupported citations, or unmet user requirements. Never remove a "
                "deterministic rule issue, approve a rejected rule, alter prices, "
                "inventory, owners, or request a write. Use only affected step keys "
                "already present in the supplied output. Required shape: "
                "{schema_version:'verification-report.v1', status:'pass|repairable|needs_input|rejected', "
                "issues:[{code,message,affected_steps,affected_artifacts,affected_skus,missing_facts,allowed_repairs}], "
                "rule_version:'shopping-rules.v1', reviewer_used:true, progress_fingerprint:null}."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "goal": goal.model_dump(mode="json"),
                    "deterministic_rules": rules.model_dump(mode="json"),
                    "task_output": _bounded_review_context(task_output),
                },
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            ),
        },
    ]


def _bounded_review_context(task_output: dict[str, Any]) -> dict[str, Any]:
    """Keep reviewer context useful without sending unbounded branch artifacts."""

    bounded: dict[str, Any] = {}
    remaining = 1_200
    for key in sorted(task_output):
        if remaining <= 0:
            break
        encoded = json.dumps(task_output[key], ensure_ascii=False, sort_keys=True, default=str)
        chunk = encoded[: min(600, remaining)]
        try:
            bounded[key] = json.loads(chunk)
        except json.JSONDecodeError:
            bounded[key] = {"truncated_summary": chunk}
        remaining -= len(chunk)
    return bounded


def _invoke_review_structured(
    candidate,
    goal: GoalSpec,
    rules: VerificationReport,
    task_output: dict[str, Any],
) -> VerificationReport:
    # The configured reasoning model may consume a sizeable hidden reasoning
    # budget before emitting the compact JSON result. Keeping this aligned with
    # the planner prevents a no-content provider timeout.
    llm = _chat_model(candidate, max_tokens=2500)
    return _coerce_review_response(
        _json_response(llm.invoke(_review_prompt(goal, rules, task_output)))
    )


def _coerce_review_response(payload: dict[str, Any]) -> VerificationReport:
    """Accept useful reviewer feedback while discarding untrusted fields."""

    status = str(payload.get("status") or "pass")
    if status not in {"pass", "repairable", "needs_input", "rejected"}:
        status = "pass"
    issues: list[VerificationIssue] = []
    raw_issues = payload.get("issues")
    if isinstance(raw_issues, list):
        for index, raw in enumerate(raw_issues[:32]):
            if not isinstance(raw, dict):
                continue
            code = str(raw.get("code") or f"reviewer_issue_{index + 1}")[:128]
            message = str(raw.get("message") or "模型复核发现需要进一步检查的结果。")[:1000]
            issues.append(
                VerificationIssue(
                    code=code,
                    message=message,
                    affected_steps=_string_list(raw.get("affected_steps"), 12),
                    affected_skus=_string_list(raw.get("affected_skus"), 16),
                    missing_facts=_string_list(raw.get("missing_facts"), 16),
                    allowed_repairs=_string_list(raw.get("allowed_repairs"), 8),
                )
            )
    return VerificationReport(status=status, issues=issues, reviewer_used=True)


def _string_list(value: Any, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item)[:256] for item in value[:limit] if item is not None]


def _json_response(message: Any) -> dict[str, Any]:
    content = getattr(message, "content", message)
    if isinstance(content, list):
        content = "\n".join(
            str(item.get("text") or item.get("content") or "")
            if isinstance(item, dict)
            else str(item)
            for item in content
        )
    text = str(content or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("structured_model_output_must_be_object")
    return value


def _chat_model(candidate: Any, *, max_tokens: int) -> Any:
    kwargs: dict[str, Any] = {
        "configurable_fields": ["model"],
        "timeout": max(1.0, candidate.total_timeout_ms / 1000.0),
        "max_retries": 0,
        "max_tokens": max_tokens,
    }
    # `thinking.type=disabled` is an OpenAI-compatible extension used by the
    # accepted GLM provider. Do not leak that provider-specific argument into
    # Anthropic or other LangChain integrations.
    if str(candidate.model).startswith("openai:"):
        kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
    return init_chat_model(candidate.model, **kwargs)


def review_with_gateway(
    goal: GoalSpec,
    rules: VerificationReport,
    task_output: dict[str, Any],
    *,
    settings: Any,
    idempotency_scope: str,
    owner_id: str,
) -> VerificationReport | None:
    """Return an optional constrained reviewer supplement.

    Deterministic rules remain authoritative. Gateway/provider failures are a
    visible no-supplement outcome and never make a failed rule pass.
    """

    gateway = _gateway(settings)

    def executor(context):
        del context
        invocation = gateway.execute(
            ModelOperation.DECISION,
            lambda candidate: ModelInvocation(
                value=_invoke_review_structured(
                    candidate,
                    goal,
                    rules,
                    task_output,
                )
            ),
        )
        return {"task_reviewer": invocation.value.model_dump(mode="json")}

    request_hash = sha256(
        json.dumps(
            {
                "scope": idempotency_scope,
                "goal": goal.model_dump(mode="json"),
                "rules": rules.model_dump(mode="json"),
                "output": task_output,
            },
            sort_keys=True,
            default=str,
        ).encode()
    ).hexdigest()
    request = RunRequest(
        operation=RunOperation.CHAT,
        user_id=owner_id,
        input_text=goal.goal_text,
        mode=RunMode.MULTI,
        idempotency_key=f"shopping-review:{request_hash}",
        policy=build_runtime_policy(settings, RunOperation.CHAT),
        budget=build_runtime_budget(settings),
        metadata={"shopping_task_reviewer": True},
    )
    try:
        result = ShopMindRuntimeHarness().run(request, executor, raise_on_error=False)
    except Exception:
        return None
    payload = result.output_data.get("task_reviewer")
    if result.error is not None or not isinstance(payload, dict):
        return None
    try:
        return VerificationReport.model_validate(payload)
    except Exception:
        return None


__all__ = ["plan_with_gateway", "review_with_gateway"]
