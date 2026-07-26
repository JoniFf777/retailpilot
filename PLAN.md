# ShopMind Agent Engineering Roadmap

Updated: 2026-07-26

## Product Direction

ShopMind will be a production-oriented **Multi-Agent Engineering reference
project**. Shopping is the scenario used to demonstrate reliable Agent
development; building a complete e-commerce platform is not the primary goal.

The final system should show how specialized Agents are orchestrated, how they
share bounded context, how memory evolves, how tools are constrained, how
humans approve sensitive actions, how Agents can later cross process boundaries,
and how the complete trajectory is evaluated and operated.

## Version Status

| Version | Status | Main outcome |
| --- | --- | --- |
| V1 | Complete | Single shopping Agent, tools, preference memory, guarded add-to-cart |
| V2 | Complete | PostgreSQL/pgvector, repositories, migrations, seed/index/smoke |
| V3 | Released | Multi-agent read path, guarded write handoff, API/CI/LangSmith evaluation |
| V4 | Complete | V4.1-V4.5 in-process runtime foundation complete |
| V5 | Complete | Slices 1-36 complete through editable, restart-safe generic HITL |
| V6 | Complete | All five slices complete; immutable commit `908b918` passed the clean committed-checkout validation matrix |

There is no planned V3.3 line. V3 is closed at `v3.0.0`; runtime work starts on
V4.

## Completion Rule

The project is complete when the satisfied V5 adapter/HITL exit conditions and
all V6 exit criteria below pass on a clean release candidate. That rule is now
satisfied: immutable implementation commit
`908b91888795f4d3d35096d6daf0592c840acdc3` passed the full clean detached
worktree matrix with empty Git status before and after validation. The current
published release remains V3 until an explicitly authorized release workflow
pushes, reviews, versions, and tags the candidate.

## V4: Agent Runtime Foundation

Goal: move from a working multi-agent graph to a reusable runtime that can
execute, persist, stream, constrain, and observe Agent runs consistently.

### V4.1 Runtime Contracts And Persistence (Complete)

- Define `RunRequest`, `RunContext`, `RunResult`, `AgentEvent`,
  `ToolCallRecord`, and error contracts.
- Add PostgreSQL conversation persistence for threads, messages, run records,
  and summaries.
- Keep `/api/chat` and `/api/chat/confirm` backward compatible while adding
  internal runtime IDs.
- Add retention fields, user/thread isolation, idempotency, repositories, and
  migration tests.

- Validation complete: full tests, PostgreSQL smoke, PostgreSQL integration, and
  V3 API handoff smoke pass.

### V4.2 Unified Agent Harness

- Introduce one lifecycle around single- and multi-agent paths.
- Centralize validation, memory loading, context construction, execution,
  retries, deadlines, cancellation, persistence, tracing, and finalization.
- Support fake models/tools, deterministic replay, and fault injection.
- Keep the current API bridge as a compatibility adapter during migration.

The first V4.2 slice is complete: request policy/budget fields now flow into the
runtime context, and the Harness enforces retryable failures, deadlines,
cancellation checks, step/tool-call budgets, structured control errors, and
single-path persistence finalization. Streaming, async cancellation, automatic
memory extraction, and compaction remain later V4 slices.

The second V4.2 slice resolves retry and optional duration, step, tool-call, and
prompt-token budgets from server-owned settings for every API-originated run.
Sensitive-tool permission is deny-first and remains exclusive to the confirmation
operation; normal chat requests cannot override it.

The third V4.2 slice enforces owner-and-operation scoped idempotency before
execution. A matching terminal run is replayed without re-running tools or
writing messages, while conflicting and in-progress keys are rejected.

The fourth V4.2 slice exposes that contract through the optional
`Idempotency-Key` header on JSON and SSE chat paths without changing V3 request
bodies.

### V4.3 Memory And Context Management

- Separate working, episodic, long-term user, and operational memory.
- Build per-Agent context slices with priorities and token budgets.
- Add conversation summaries, deduplication, provenance, expiry, and deletion.
- Prevent cross-user and cross-thread memory leakage.

The first V4.3 slice is complete: `runtime_memory_records` stores explicit
working, episodic, long-term, and operational records with owner/thread scope,
provenance, priority, expiry, soft deletion, and token estimates. The runtime
Context Manager deduplicates and bounds messages, summaries, and explicit
records into an inspectable `ContextSlice`; automatic memory extraction and
compaction remain future work.

### V4.4 Async Streaming And Runtime Control

- Stop invoking the graph synchronously inside the async FastAPI route.
- Add SSE for lifecycle, token, tool, confirmation, error, and final events.
- Add disconnect cancellation, deadlines, concurrency limits, and bounded event
  buffers.
- Keep the existing complete JSON response for non-streaming clients.

The second V4.4 slice adds local in-process stream admission control and bounded
event queues. Queue pressure requests Harness cancellation and a full local
limit returns HTTP 429; token-level model streaming, hard interruption of
synchronous providers, and distributed rate limiting remain future work.

### V4.5 Tool Gateway And Policy Sandbox

- Evolve V3 allowlists into a centralized capability registry.
- Validate schemas/arguments; enforce timeouts, result limits, database roles,
  URL allowlists where relevant, and per-run budgets.
- Generalize pending actions into an action registry for sensitive writes.
- Keep arbitrary code execution out of scope unless a future Code Agent makes a
  process/container sandbox necessary.

The first V4.5 slice is complete: `ToolGateway` centralizes V3 capabilities and
performs Pydantic argument validation, user/thread ownership checks, sensitive
tool policy checks, output limits, and per-run tool budgets before delegation.
Successful calls produce structured `ToolCallRecord` audit data. A generic
action registry, database/network isolation, and OS-level sandbox remain future
work.

The second V4.5 slice is complete for the existing write path: typed action
definitions now select confirmation/cancellation tools, pending actions persist
risk, preview, metadata, and expiry fields, and confirmation/cancellation use
owner/thread validation plus row-locked state transitions. Generic action types
and database/network isolation remain future work.

The third V4.5 slice routes the confirmation boundary through `ToolGateway` with
an explicit `confirmation_boundary` capability and approved sensitive-tool
policy. Gateway-generated `ToolCallRecord` data now survives Harness result
normalization and persistence; ordinary chat requests retain the default deny
policy.

The fourth V4.5 slice is complete for the V3 read graph: `PermissionedTool`
delegation now uses `ToolGateway.invoke` for the actual call, including result
limits and stable capability checks, while preserving legacy call arguments.

The fifth V4.5 slice passes the per-run `RunContext` into freshly bound V3 read
tool wrappers. Ownership checks and tool budgets therefore apply to actual graph
execution without sharing mutable context between requests.

The sixth V4.5 slice collects gateway records from read-tool execution and emits
ordered `tool.call.completed` audit events before the terminal run event. The
same records are now available to persistence and streaming without changing
the public JSON response.

The seventh V4.5 slice records attempted tool failures with a completed
`ToolCallRecord`, a safe error code and exception type, then emits
`tool.call.failed` before `run.failed`. The Harness persists that record without
exposing underlying provider exception text through the compatibility API.

The eighth V4.5 slice adds a typed `ActionTransitionRequest` and routes existing
pending-action confirmation/cancellation through the registry. The registry now
validates action identity and rejects duplicate definitions before selecting a
transition tool; generic action execution and database/network isolation remain
future work.

The ninth V4.5 slice also validates action creation through the same registry
before the V3 write handoff can create a pending action. Registry rejection has
an internal safe failure path; normal add-to-cart responses and confirmation
semantics remain unchanged.

The tenth V4.5 slice routes `prepare_add_to_cart` through the Tool Gateway as a
non-sensitive `WRITE` capability that creates a pending action, while confirm
and cancel remain sensitive capabilities. Its audit record now joins the shared
Harness result without changing the public response.

The eleventh V4.5 slice adds cooperative execution controls at the gateway
boundary. A run that is already cancelled, past its deadline, or past its
duration budget skips tool invocation with a structured audit record; per-tool
capability duration limits are recorded as audit metadata after the provider
returns, without rewriting a completed side effect into a false failure.

The twelfth V4.5 slice makes action and tool capability registration fail closed:
blank names and duplicate definitions are rejected both during initialization
and during later registration, so a policy cannot be silently replaced by
construction order.

The thirteenth V4.5 slice adds a typed capability-owned resource policy.
Registered V3 catalog, document, and preference tools declare database `READ`;
prepare, confirm, and cancel cart actions declare database `WRITE`. The policy
is retained in tool audit records. Future network tools must explicitly enable
network access and provide a bare lowercase HTTPS host allowlist; no network
tool or client-controlled resource authorization is introduced in this slice.

The fourteenth V4.5 slice replaces production reliance on naming conventions
with an explicit V3 capability policy manifest. The multi-agent permission
wrapper, write handoff, and API confirmation gateway now require every allowed
production tool to declare its side-effect class, confirmation requirement, and
resource policy; an unclassified entry fails during Gateway construction.

The fifteenth V4.5 slice adds Agent ownership to that manifest. Strict Gateway
construction now rejects both undeclared tools and allowlist drift that assigns
a declared tool to a different Agent, keeping capability, resource, and
Agent-level policy aligned at the production boundary.

The sixteenth V4.5 slice makes the production manifest read-only and tests it
against the real V3 allowlist rather than a duplicated fixture. Runtime code
cannot mutate capability policy entries accidentally, and configuration drift
is checked against the same allowlist used by the permission wrapper.

The seventeenth V4.5 slice freezes the nested `ToolResourcePolicy` Pydantic
contract as well as the manifest mapping. Database and future network access
declarations therefore cannot be modified through a manifest entry after
startup policy construction.

The eighteenth V4.5 slice validates confirmation semantics alongside resource
semantics: sensitive writes must declare confirmation, while read-only and
side-effect-free capabilities cannot claim a confirmation requirement. Invalid
combinations fail when a Gateway is built.

The nineteenth V4.5 slice carries each capability's confirmation requirement
into `ToolCallRecord` and Harness audit events. Persisted runs, SSE consumers,
and later evaluators can therefore determine a tool's confirmation posture from
the recorded execution rather than reloading the current manifest.

### V4 Exit Criteria

- Multi-turn conversations survive process restarts in PostgreSQL.
- Every run uses the same Harness and stable event contract.
- Streaming clients can cancel without leaving an active run or partial write.
- Context construction is inspectable, bounded, and isolated by user/thread.
- Unauthorized tools and malformed arguments fail before side effects.
- Default tests remain model-independent; PostgreSQL and API smoke pass.
- Migration, rollback, API, and evaluation documents exist.

## V5: Advanced Multi-Agent Collaboration

Goal: demonstrate collaboration patterns beyond a fixed router.

- Combine deterministic policy routing with planner-driven task decomposition.
- Add bounded parallel fan-out/fan-in for independent research tasks.
- Standardize inter-Agent task/result envelopes with typed schemas.
- Add evidence provenance, contradiction detection, and conflict rules.
- Generalize HITL to approve, edit, reject, resume, and expire actions.
- Add `InProcessAgentAdapter` first and an A2A/HTTP adapter behind the same
  interface; demonstrate one remote specialist rather than splitting every
  graph node into a service.
- Enforce depth, step, token, cost, and wall-clock budgets across delegation.

V5 is complete when the same task can use an in-process or remote specialist
without changing Supervisor business logic, and both paths share safety,
tracing, and evaluation contracts.

The first V5 slice is complete: `AgentTask` and `AgentResult` provide typed
delegation envelopes with run/thread/user/trace identity, context references,
budgets, output schema expectations, evidence, usage, errors, and child traces.
`InProcessAgentAdapter` validates recipient and task-result identity before
calling a local handler. It does not introduce async fan-out or a remote
transport.

The second V5 slice routes the existing `product_agent` through that local
adapter. A typed product-task input/output bridge preserves the V3 graph state,
tool selection, route order, and public response while establishing the first
real specialist migration path.

The third V5 slice routes the existing `rag_agent` through the same local
adapter boundary. Its typed bridge preserves V3 RAG tool filtering and state
updates while mapping retrieved citation document IDs into
`AgentResult.evidence_references`.

The fourth V5 slice routes the existing `preference_agent` through the local
adapter too. Its bridge passes the typed task's `user_id` unchanged to the
existing read tool, preserving the V3 owner scope. All current read specialists
now use the adapter boundary without changing the graph routes or public API.

The fifth V5 slice makes delegated-task limits executable. `AgentTask` now has
validated parent/depth identity, and the graph shares a thread-safe
`DelegationBudgetGuard` across local adapters to reject tasks exceeding trusted
depth or per-parent child-task limits before an Agent handler runs. The current
V3 graph still submits root tasks only; parallel fan-out remains out of scope.

The sixth V5 slice carries RAG's typed document evidence references back into
the graph state. The Decision Agent records a conservative product-document
scope mismatch when product candidate IDs and product-document IDs have no
overlap. This is observability only: it does not alter the answer, routes, or
write policy.

The seventh V5 slice defines typed `EvidenceConflict` and `EvidenceResolution`
contracts and makes that mismatch fail closed. Decision excludes the mismatched
RAG summary, retains non-conflicting summaries, records evidence reference IDs,
and requests product-model clarification. Matching evidence and all existing V3
write safeguards remain unchanged.

The eighth V5 slice adds typed `AgentPlanStep` and `AgentExecutionPlan`
contracts with unique-step, dependency-reference, cycle, and execution-mode
validation. Supervisor maps deterministic read routes into logically independent
steps, but the emitted plan remains sequential with `max_parallelism=1`; the V3
dispatcher and public API behavior are unchanged.

The ninth V5 slice adds typed plan-step/plan results and a local
`BoundedPlanExecutor`. Parallel execution is disabled by default, accepts only
independent steps when explicitly enabled, caps workers by plan parallelism, and
fans results in using plan order with deduplicated evidence and aggregated
usage. Failures become sanitized `RunError` records; the executor is not yet
wired into the V3 graph.

The tenth V5 slice adds server-owned parallel-read settings, bounded to three
workers, plus isolated per-step state construction and deterministic graph-state
fan-in mapping. Isolation preserves request identity/current-turn input without
sharing specialist summaries or mutable traces. The settings remain inert at
the graph boundary until shared runtime/tool accounting is concurrency-safe.

The eleventh V5 slice makes shared runtime/tool accounting concurrency-safe.
`RunContext` owns a private, non-serialized metadata lock and stable snapshots;
the Tool Gateway atomically reserves budget before execution and orders audit
records by `audit_sequence`. Concurrent calls cannot overrun the per-run tool
budget or lose records. The graph feature gate remains disconnected.

The twelfth V5 slice connects the server-owned feature gate to the multi-agent
graph. Multi-route independent reads can use bounded parallel execution only
when explicitly enabled; default, single-route, and write-handoff flows remain
sequential. Each specialist receives isolated state, and typed fan-in preserves
plan-order summaries, tools, evidence, safety flags, and traces. Graph-level
tests cover sequential equivalence, partial failure, atomic tool budgets, and
pre-execution cancellation without changing the V3 public API.

The thirteenth V5 slice adds cooperative mid-execution cancellation. Harness
callbacks are bound to `RunContext` as non-serialized local controls, plan
workers check cancellation before starting each queued step, and concurrent
plan/step lifecycle events receive one atomic sequence. Already-running
synchronous calls finish normally; their completed or failed tool audit records
survive cancelled-run finalization and persistence. No thread or provider call
is force-terminated.

The fourteenth V5 slice adds an injectable `AgentPlanner` protocol and a
`ValidatedProviderPlanner`. The provider receives the Supervisor routes and a
server-compiled baseline plan, but its proposal is treated as untrusted. Route
order, step IDs, intents, dependencies, run identity, execution mode, and
parallelism must exactly match policy; otherwise the runtime records a sanitized
reason and uses deterministic fallback. Accepted proposals are recompiled from
the baseline, so provider IDs, types, and arbitrary metadata never execute.
There is no production planner setting or model call in this slice.

The fifteenth V5 slice adds a lazy LangChain structured-output provider behind
`SHOPMIND_AGENT_PLANNER=llm`. The default and every invalid value remain
`deterministic`; enabling LLM planning does not bypass canonical validation or
deterministic fallback. Router and planner settings are independent, model
initialization waits for an actual read plan, and write-handoff/empty-route
plans never call the provider. Model-independent fake structured-output tests
cover schema use, metadata, bridge selection, and fallback behavior.

The sixteenth V5 slice adds a model-independent planner policy evaluation with
10 fixed trajectories and 70 checks. It covers accepted sequential/parallel
plans, route and dependency injection, execution-mode and parallelism
escalation, run-identity spoofing, malformed output, provider failure, and the
write-path zero-call guard. The local CLI emits text or JSON, returns non-zero
on failures, and never requires LangSmith or model credentials. Current result:
`10/10` cases and `70/70` checks.

The seventeenth V5 slice promotes that deterministic suite to a required default
CI gate. CI pins `SHOPMIND_AGENT_PLANNER=deterministic`, publishes the readable
summary to the workflow report, and uploads the complete JSON result as the
`v5-planner-policy-eval` artifact. The CLI writes the JSON artifact atomically,
including failure details before returning a non-zero gate status, and does not
initialize a model or read provider credentials.

The eighteenth V5 slice adds a model-independent graph plan trajectory replay
evaluation. Six initial scenarios pass through the production compiled graph,
typed specialist adapters, Tool Gateway, bounded executor, and deterministic
fan-in: complete parallel execution, partial specialist failure, atomic shared
tool/step budget exhaustion, pre-execution cancellation, and cooperative queued-
step cancellation. Each replay checks 12 normalized lifecycle, ordering, budget,
audit, and Decision fan-in invariants. Thread completion order, generated IDs,
and timings are excluded from the versioned artifact contract. The replay wraps
graph invocation in a local tracing-disabled context, so an externally enabled
LangSmith setting cannot turn the offline suite into a network call. The
original result was `6/6` cases and `72/72` checks. The production bounded
executor now
copies the parent execution context separately for each worker, so request-local
context variables and the offline tracing boundary survive thread fan-out.

The nineteenth V5 slice promotes graph trajectory replay to the default CI gate.
It runs after planner policy evaluation even when an earlier step failed, adds
its readable report to the workflow summary, and uploads the versioned JSON as
`v5-plan-trajectory-eval`. Planner and trajectory artifacts remain separate so
policy-validation failures and execution-lifecycle failures can be diagnosed
independently without enabling model calls or external tracing. Full regression
also exposed and closed an SSE finalization race: accepted worker events are
flushed before final result/error and stream termination enter the queue.

The twentieth V5 slice makes `RunBudget.max_steps` executable before local
specialist work begins. The shared `DelegationBudgetGuard` takes a deep server-
trusted budget snapshot, applies the stricter task sub-budget, scopes idempotent
admissions by `(run_id, task_id)`, and atomically reserves root and child Agent
tasks across adapters. Plan step IDs now flow into typed task IDs on sequential
and parallel paths. Exhaustion fails before handler/tool execution with the
stable sanitized code `plan.step_budget_exceeded`; Harness post-run validation
remains the stricter whole-run step check.

The twenty-first V5 slice aggregates `RunUsage` across typed specialist results,
including input, output, total tokens, and USD cost. Sequential graph state and
bounded-parallel fan-in carry the same structured measurements into the Harness,
which persists them on `RunResult`. A shared per-run guard reconciles actual
post-execution usage atomically and applies the stricter server-owned or task
ceiling. It never accepts provider-supplied policy limits. If a configured
metric is missing anywhere in the run, execution fails closed with a sanitized
usage-unavailable error rather than summing a misleading partial value. Step
and tool budgets remain pre-execution reservations; token/cost reconciliation
is post-execution because actual usage is not known earlier.

The twenty-second V5 slice enforces delegation time boundaries directly in the
shared local adapter guard. Admission uses the earliest task, task-budget,
server-budget, or trusted request deadline and the stricter task/server maximum
duration measured from the trusted run start. The guard checks again after a
synchronous handler returns or raises; completed usage remains recorded before
a post-execution timeout is surfaced. Stable `plan.deadline_exceeded` and
`plan.duration_budget_exceeded` errors use the timeout source and identify
admission versus reconciliation without exposing handler details. This does not
force-terminate an in-flight synchronous call. The offline compiled-graph replay
now includes expired deadline and duration cases that fail before specialist
tools, bringing the gate to `8/8` cases and `96/96` checks.

The twenty-third V5 slice introduces a runtime-checkable, transport-neutral
`AgentAdapter` protocol over the existing typed `AgentTask`/`AgentResult`
envelopes. `invoke_agent_adapter` is the common consumer boundary: it rejects a
recipient mismatch before invoking a transport and rejects loose or mismatched
results afterward. Product, RAG, and preference graph bridges now depend on the
protocol rather than the concrete local class; their factories still return
`InProcessAgentAdapter`. A conformance suite covers structural implementations,
pre-transport identity rejection, typed result enforcement, failed-result
preservation, and a protocol-only graph bridge. No HTTP client, service
discovery, serialization transport, or remote A2A behavior is enabled.

The twenty-fourth V5 slice adds an immutable `AgentAdapterRegistry` keyed by
exact normalized recipient names. Construction rejects non-conforming adapters,
duplicates, and malformed names; unknown recipients fail closed. The production
graph builds its registry through a server-owned factory that registers exactly
the product, RAG, and preference `InProcessAgentAdapter` instances with one
shared trusted `DelegationBudgetGuard`. Graph node binding now resolves through
this registry rather than constructing adapters independently. No registry is
accepted from API/client input, and no remote adapter can yet enter the
production factory.

The twenty-fifth V5 slice separates transport execution from delegation policy.
`InProcessAgentAdapter` now only invokes and validates its local handler.
`PolicyEnforcedAgentAdapter` decorates any conforming transport with the shared
guard lifecycle: pre-invocation admission, exception-time reconciliation,
typed result identity validation, and post-result usage/time reconciliation.
All specialist factories return this decorator around their in-process
transport, and the production registry still shares one trusted guard across
the three wrappers. A protocol-only fake transport proves step limits apply
before its second call, so policy no longer depends on local transport code.

The twenty-sixth V5 slice makes that policy layer mandatory at the production
registry boundary. `AgentAdapterRegistry` retains a transport-neutral default
for contract tests and future adapter development, but its explicit
`require_policy` mode rejects every unwrapped transport during construction.
The server-owned ShopMind registry always enables this mode, exposes the mode
as read-only diagnostic state, and continues to register only the three
policy-wrapped specialists. A focused contract test proves a structurally valid
bare transport cannot enter a policy-required registry.

The twenty-seventh V5 slice hardens failures across the Registry, graph, and
Harness boundaries. Unknown executor exceptions now persist a stable safe
message instead of `str(exc)`, while adapter contract, delegation time, usage,
and general budget failures map to typed codes and sanitized details. Existing
Tool Gateway error mapping remains unchanged. Fault injection covers a private
transport exception and a wrong task ID through the policy-required production
registry and complete parallel graph: both become `plan.step_failed`, successful
specialists still fan in, and private payload details do not enter graph output.
A registry-level timeout test also proves exception-time policy reconciliation
still takes precedence over the underlying transport error.

The twenty-eighth V5 slice adds a typed, sanitized transport failure contract.
`AgentTransportError` accepts only server-defined unavailable, timeout, or
protocol-error codes and requires an explicit boolean `retriable` value; safe
messages and error source are derived internally, so transports cannot attach
endpoint text to persisted failures. The Harness maps this contract into its
existing bounded whole-executor retry loop, and the plan executor preserves the
same code, source, and retriability in deterministic partial results. Contract,
retry, timeout, sequential-plan, and complete parallel-graph tests cover the
boundary. Parallel plan steps are classified but are not automatically replayed.

The twenty-ninth V5 slice defines task-level retry ownership and safety without
enabling replay. Frozen `AgentTaskRetryPolicy` permits only disabled single
attempts or Plan Executor-owned retries, caps attempts at three, requires a
closed typed transport failure set, preserves task identity, and requires every
attempt to be budget-accounted. Retriable tasks must carry the runtime-derived
SHA-256 idempotency key for their exact `(run_id, task_id)`; caller-selected keys
fail validation. Product, RAG, and preference bridges now assign that stable key
to every task while retaining the default disabled/one-attempt policy. The next
prerequisite is measured failed-attempt usage, so no specialist replay occurs in
this slice.

The thirtieth V5 slice closes failed-attempt accounting before replay.
`AgentTransportError` now requires typed `RunUsage` covering at least one
attempt. `PolicyEnforcedAgentAdapter` reconciles that usage through the shared
guard before the transport error can escape; missing configured metrics or a
cumulative ceiling violation therefore overrides retriability and fails closed.
`AgentPlanStepResult` retains usage even without an `AgentResult`, deterministic
fan-in includes failed attempt usage, and the Harness aggregates failed and
successful executor attempts before budget checks and persistence. A shared
usage aggregator preserves unavailable metrics instead of treating them as
zero. Specialist replay remains disabled.

The thirty-first V5 slice enables server-owned bounded specialist replay while
preserving the disabled default. `RuntimePolicy`, canonical plan steps, and
generated `AgentTask` envelopes carry the same frozen retry policy. The setting
`SHOPMIND_AGENT_TASK_MAX_ATTEMPTS` defaults to one and is capped at three;
values above one allow only typed unavailable and timeout failures. The Plan
Executor reuses the exact step/task identity and runtime-derived idempotency key,
checks cancellation before another attempt, and aggregates every failed and
successful attempt without converting unavailable metrics to zero. Validated
planner proposals cannot change the policy. Explicit retry opt-in also sends a
sequential read plan through the same typed executor, while the default V3
dispatcher path remains unchanged.

The thirty-second V5 slice makes that replay observable and deterministic under
fault injection. `AgentPlanAttemptEvent` provides a frozen structured payload
for started/completed/failed attempts and retry scheduling, start, success,
exhaustion, non-retriable, budget-blocked, and cancellation decisions. The Plan
Executor emits those events in per-step order through the existing Harness
boundary, so one monotonic `AgentEvent` sequence is persisted and mirrored to
SSE consumers. Five fixed retry scenarios extend the production compiled-graph
replay to `13/13` cases and `195/195` checks. The artifact schema is now
`shopmind.plan-trajectory-eval.v2`; it remains model-, database-, credential-,
and LangSmith-independent. The server default stays one attempt.

The thirty-third V5 slice adds a real synchronous `HttpAgentAdapter` without
changing production selection. Constructor-only server configuration enforces a
fixed HTTPS endpoint and host allowlist, disables redirects, bounds timeout and
decoded response bytes, propagates run/task/trace/idempotency identity, and
parses the existing typed task/result schemas. Network, timeout, HTTP status,
malformed/oversized payload, and identity failures map to the closed sanitized
transport contract with measured attempt usage. Unit tests and the new
`shopmind.adapter-equivalence-eval.v1` gate use `httpx.MockTransport`; default
CI has no external specialist or network dependency.

The thirty-fourth V5 slice makes one independent ownership boundary executable.
Server-owned settings can explicitly select HTTP transport for `rag_agent`
only; the product and preference specialists remain in-process. Incomplete
remote configuration fails graph construction closed. A remote RAG adapter is
still wrapped by `PolicyEnforcedAgentAdapter` and shares the same trusted guard,
while the Supervisor, canonical plan, graph state, Decision Agent, public API,
and retry owner remain unchanged. The default is `in_process`, credentials are
secret-valued configuration, and a compiled-graph test proves transport
location does not change route or fan-in contracts.

The thirty-fifth V5 slice turns the typed Action Registry into an executable
multi-action HITL boundary. `/api/chat/confirm` now resolves action type from
the server-owned pending record under user/thread scope before dispatching only
a registered handler; API callers still provide only action ID and direction.
`save_preference` is the second real action: write handoff prepares a medium-risk
record without mutating long-term preferences, confirmation writes the
preference transactionally, and the shared cancellation handler rejects it
without side effects. Add-to-cart remains byte-for-byte API compatible.
`action.prepared/confirmed/cancelled/expired/failed` events use the Harness-owned
sequence and therefore share persistence and SSE delivery. The deterministic
`shopmind.action-lifecycle-eval.v1` gate covers confirm, cancel, expiry,
cross-user/thread denial, duplicate transition and malformed handler input at
`7/7` cases and `28/28` checks.

The thirty-sixth V5 slice closes the generalized HITL exit condition. Action
definitions own exact, extra-forbidden edit schemas: add-to-cart accepts only a
positive integer `quantity`, while save-preference accepts only its normalized
type and non-blank value. `/api/chat/confirm` adds an optional
`updated_arguments` object but still derives action type, owner, thread, risk,
expiry and handler from the persisted record. Edits and final confirmation run
under the same row lock and transaction; cancellation cannot carry edits.
Successful resumes emit ordered `action.resumed`, optional `action.edited`, and
terminal events through the Harness, so they persist and stream with the run.
PostgreSQL integration proves prepare/restart/edit/confirm,
prepare/restart/reject, expired resume and idempotent API replay without graph
memory. The `shopmind.action-lifecycle-eval.v2` gate now passes `10/10` cases
and `60/60` checks. With canonical planning, bounded fan-out/fan-in, evidence
conflict policy, shared budgets, local/HTTP adapter equivalence and generalized
HITL all executable, the V5 exit condition is satisfied in this worktree.

## V6: Evaluation And Production Reference

Goal: make quality, resilience, and operating cost measurable.

- Per-Agent, router, answer, trajectory, multi-turn, memory, and safety datasets.
- Simulation, adversarial cases, record/replay, fault injection, and regression
  comparison.
- Online sampling, annotation queues, evaluator calibration, and data flywheel.
- Redis distributed rate limits, concurrency controls, deduplication, caching,
  and run coordination where one process is insufficient.
- Authentication/authorization integration points, PII handling, audit logs,
  retention/deletion jobs, dashboards, alerts, deployment runbook, and SLOs.
- A compact reference client for streaming, HITL resume, memory, and trace
  inspection without becoming a storefront project.

### Planned V6 Slices

1. **Evaluation catalog and regression comparison**: versioned per-Agent,
   router, answer, trajectory, multi-turn, memory, safety, latency, token, and
   cost datasets with baseline comparison and machine-readable CI artifacts.
2. **Resilience and record/replay**: deterministic provider/tool/transport fault
   injection, retry/cancellation/idempotency trajectories, adapter equivalence,
   and recovery assertions across process restarts.
3. **Runtime operations**: Redis-backed distributed admission/rate limits,
   duplicate suppression and bounded caching only where multi-process behavior
   requires them; local mode remains available for development.
4. **Security and data governance**: authentication/authorization integration,
   PII-safe logging, audit inspection, retention/deletion enforcement, and
   documented trust boundaries.
5. **Observability and reference deployment**: metrics, dashboards, alerts,
   SLOs, deployment/rollback runbooks, production configuration validation, and
   a compact client covering SSE, HITL resume, memory, and trace inspection.

The first four V6 slices (global Slices 37-40) are implemented. The closed
`shopmind.evaluation-catalog.v1` manifest admits only eight server-registered,
model-independent runners and requires coverage for per-Agent, router, answer,
trajectory, multi-turn, memory, safety, latency, token, and cost dimensions.
Its accepted `shopmind.evaluation-baseline.v1` locks suite schemas and minimum
case/check counts. `evaluation/run_catalog_eval.py` runs or reuses the existing
V5 artifacts, produces a versioned candidate, and fails non-zero when quality
or safety falls, latency/token/cost regression counts rise, a suite disappears,
or a schema/count contract shrinks. Slice 2 adds a closed six-case resilience
suite over provider fallback, tool failure, transport retry success,
cancellation before retry, idempotent restart replay, and action restart/resume.
Normalized owner-scoped trajectories retain ordered identities and safe event
classifications while hashing raw request/result/output/debug/tool payloads.
The current gate passes `8/8` suites, `61/61` cases, `488/488` suite checks, and
`48/48` baseline comparisons. CI
publishes the readable summary and machine-readable catalog artifact separately
without accepting a new baseline automatically.

The SQLite fresh-engine and offline CI boundaries are passing. Two additional
PostgreSQL assertions exercise retry/idempotency and action recovery through a
new engine/session factory. The pre-governance PostgreSQL integration passed
`18/18`, and the V3
API handoff remains `3/3`; no replacement container was created.

V6 Slice 3 is complete with a transport-neutral `RuntimeCoordinationBackend`
contract and a bounded thread-safe local implementation. Admission uses opaque,
renewable TTL leases; fixed-window rate limits, duplicate claims and bounded
TTL/LRU cache entries use only fingerprinted subject/key identities. Backend
cardinality and cache value size are bounded, exhaustion fails closed, and
cache values must be JSON-serializable. The second substage adds server-owned
backend selection and moves SSE admission behind token-specific renewable
leases. `local` remains the default; unknown legacy values normalize to local,
while an explicit `redis` selection fails closed if its secret URL, client, or
connection is unavailable. The third substage implements versioned same-slot
Redis keys and atomic Lua admission, rate-limit, duplicate-claim and TTL/LRU
cache operations. A deterministic local/Redis equivalence gate passes `5/5`
cases and `18/18` checks and is registered as the seventh V6 catalog suite;
the catalog passes `56/56` cases, `446/446` checks and `43/43` baseline checks.
The default-skipped real Redis gate has also passed against an isolated DB/key
scope. Two clients share state, eight concurrent contenders respect an exact
three-lease limit, server TTL expiry restores capacity, and rate-limit,
deduplication and cache state behave across clients. The test cleans only its
random versioned key scope. Combined PostgreSQL/Redis integration passes
`19/19`.

V6 Slice 4 is complete. It started with a closed `AuthenticatedPrincipal` and
`IdentityBoundary`. Server configuration selects either the backward-compatible
`development_payload` adapter or an explicit `trusted_header` adapter; API
payloads cannot select providers, roles or scopes. Trusted-header mode binds a
fixed proxy-authenticated subject to the existing owner field before Agent,
stream admission or action-confirmation execution. Missing identity returns
401 and owner mismatch returns 403 with stable detail. Raw subject IDs are
excluded from model repr; a namespaced SHA-256 fingerprint is available for
future audit records.

The second Slice 4 substage adds the frozen
`shopmind.governance-audit.v1` contract and `GovernanceAuditFactory`.
Authentication, tool, action, memory and deletion operations have closed
category/decision/reason combinations. Actor, owner, thread, run and resource
identities are domain-separated SHA-256 fingerprints. Metadata is an
extra-forbidden typed allowlist; it has no fields for raw messages, arguments,
previews, credentials, headers or connection URLs. Existing `ToolCallRecord`
conversion copies only server-owned capability/policy fields, bounded numeric
facts and a validated existing argument fingerprint, and discards arbitrary
result metadata. This substage is model-independent.

The third Slice 4 substage persists those closed facts in
`governance_audit_records` at Alembic head `0007_governance_audit`. The table
has no raw user/thread/run/resource columns or foreign keys: it stores only
fingerprints, closed classification fields, allowlisted JSONB metadata and
explicit occurrence/creation/expiry timestamps. Repository append is immutable,
inspection requires an exact owner fingerprint and is newest-first/bounded,
expired facts are hidden, and the existing runtime cleanup command hard-deletes
them only after their audit-specific retention window. SQLite contract tests,
fresh-session PostgreSQL verification and read-only smoke pass; PostgreSQL
integration reached `19/19`. At that substage production authentication/tool/
action/memory boundaries did not emit records, so repository delivery alone did
not change V3 request/response or failure behavior.

The fourth Slice 4 substage adds a server-owned, default-off
`SHOPMIND_GOVERNANCE_AUDIT_ENABLED` emission path. Authentication allow/deny
decisions are emitted at the identity boundary. The Harness projects only typed
`ToolCallRecord` facts, closed action lifecycle events and selected persisted
memory items; it ignores arbitrary event fields, current-request memory content
and Tool Gateway result metadata. Run/tool/action/memory source identities
produce deterministic audit IDs, so an emission replay is an immutable
duplicate rather than a second row.

Governance emission uses an independent batch transaction after ordinary
runtime persistence. Storage failure rolls back that audit batch, returns/logs
only `storage_unavailable`, and cannot change an authentication HTTP decision,
Agent result, action transition or V3 response. The default stays disabled
until operators explicitly opt in; API payloads cannot select it. Focused API,
Harness and failure tests pass, and fresh-session PostgreSQL coverage verifies
the emitted action/tool batch without retaining raw identities.

The fifth Slice 4 substage adds authenticated owner-data inspection, correction
and deletion. Four additive endpoints provide a bounded inventory plus memory
inspection, exact-owner memory correction, exact-owner memory hard deletion,
and explicitly confirmed full owner-data deletion. Full deletion covers
preferences, cart items, pending actions, candidate contexts, conversations,
messages, runs/events, summaries, idempotency records and memory. It does not
touch the product/document catalog, inherited customer/order seed data, or
fingerprint-only governance audit rows.

All owner-data operations bind the requested owner before storage access.
Correction clears stale derived JSON/provenance and records an explicit
owner-correction source. Full deletion is one exact-owner transaction and
requires a UUID deletion request plus literal confirmation. When governance
emission is enabled, memory inspect/correct/delete and deletion request/execute
facts use the existing PII-safe schema and independent retention. Audit failure
does not rewrite a successful owner-data result, while storage failure is
reduced to a stable HTTP 503 without backend details. SQLite API/service tests
and fresh-session PostgreSQL verification cover owner isolation, hard deletion,
duplicate-by-effect execution and retained audit facts.

The sixth Slice 4 substage adds the production-facing `signed_header` adapter
behind the same `IdentityBoundary`. A trusted ingress supplies the existing
subject header plus a canonical epoch timestamp, one-time nonce and lowercase
HMAC-SHA256 signature. Server-owned configuration requires a masked secret of
at least 32 characters, bounds assertion age to at most five minutes and keeps
the compatibility `development_payload` default unchanged. Missing, partial,
invalid, expired, replayed and coordination-backend failures all fail closed
through the existing public 401 contract; exact owner mismatch remains 403.

Replay claims contain only a domain-separated fingerprint and use the existing
coordination backend. The bounded local backend supports one process; explicit
Redis mode makes the one-time claim atomic across API processes. Real
two-client Redis coverage proves first-accept/second-reject behavior and verifies
that subject, nonce, signature and signing secret are absent from coordination
keys. This adapter performs no remote IdP/JWKS HTTP call and introduces no
payload role or scope claims. Current combined PostgreSQL/Redis integration
passes `25/25`.

The seventh Slice 4 substage makes audit-emission failure observable without
making it business-critical. The process-local, thread-safe
`shopmind.governance-audit-monitor.v1` snapshot counts closed emission calls,
storage attempts, requested/persisted/duplicate records, skips, failures,
consecutive failures, and alert/recovery transitions. It stores no audit
record, identity, request, action, memory, credential, exception or connection
detail.

`SHOPMIND_GOVERNANCE_AUDIT_ALERT_FAILURE_THRESHOLD` is server-owned, defaults
to three consecutive failures and is capped at 100. Crossing the threshold
emits a structured sanitized active alert; the next persisted or duplicate
commit emits recovery and resets the streak. The additive
`GET /api/health/governance-audit` endpoint reports the process snapshot and
whether audit emission is enabled. It remains HTTP 200 even while degraded so
optional audit storage cannot remove a healthy business process from service.
Operators must scrape every API process and keep the endpoint on their internal
operations boundary. Audit emission remains default-off and requires an
explicit operator opt-in.

The eighth and closing Slice 4 substage adds
`shopmind.governance-lifecycle-eval.v1`. Five deterministic, offline scenarios
exercise signed identity acceptance/replay/owner denial, exact-owner memory
inspection/correction/deletion, full owner deletion and duplicate-by-effect
execution, audit alert/recovery, and immutable audit persistence/idempotency.
The suite passes `5/5` cases and `42/42` checks without a model, network,
credential, Redis, PostgreSQL or LangSmith dependency. It is the eighth closed
catalog runner and is locked by the explicitly added
`shopmind-v6-slice4-accepted` baseline. The complete gate passes `8/8` suites,
`61/61` cases, `488/488` suite checks and `48/48` baseline checks. CI runs and
uploads the governance artifact before reusing it in the catalog gate; runtime
code never updates an accepted baseline.

V6 Slice 5 has started with the frozen
`shopmind.production-preflight.v1` static configuration contract.
`SHOPMIND_DEPLOYMENT_PROFILE=production` activates six closed checks for
identity trust, single/multi-replica coordination, audit emission, RAG
transport, retention cleanup and bounded runtime limits. The development
profile remains the default and reports `not_applicable`, preserving all
released behavior.

Production accepts signed identity or an explicitly attested trusted proxy;
multi-replica topology requires configured Redis, while local remains valid for
one replica. Audit emission and external cleanup scheduling must be explicitly
enabled. In-process RAG remains valid; HTTP requires a query-free HTTPS endpoint
whose host is in the server allowlist. Duration, step, tool-call, total-token
and cost limits must all be positive. An explicitly selected production profile
that fails any check prevents application creation with one sanitized error.

`scripts/check_production_config.py`, `GET /api/health/preflight`, and the CI
artifact expose only check IDs, categories and closed reason/status values;
they never expose URLs, hosts, tokens, signing secrets, database settings or
raw validation exceptions. This substage performs no network or storage probe.
Proxy enforcement remains a deployment responsibility.

The second Slice 5 substage adds the frozen
`shopmind.deployment-readiness.v1` live contract. Its five checks cover the
static preflight result, PostgreSQL connectivity, exact migration head,
selected local/Redis coordination reachability, and recent runtime-cleanup
success evidence. `GET /api/health/readiness` returns HTTP 200 only when every
applicable check passes and HTTP 503 otherwise. `development` still probes
PostgreSQL/migration and local coordination, while static configuration and
retention evidence are explicitly `not_applicable`.

`cleanup_runtime_persistence.py` writes the minimal
`shopmind.runtime-cleanup-evidence.v1` marker atomically only after its database
transaction commits. Production readiness requires an operator-selected marker
path and a bounded maximum age; missing, malformed, stale or future evidence
fails closed. `scripts/check_deployment_readiness.py` and the PostgreSQL
integration workflow publish the same value-free report. Database/Redis URLs,
hosts, migration values, paths and raw exceptions are never report fields.

The third Slice 5 substage adds `shopmind.service-metrics.v1`,
`shopmind.service-slo.v1`, and the combined `shopmind.service-health.v1`
snapshot. The common Harness observes each terminal chat/confirmation request
exactly once, including raised failures and idempotent replays. Process-local
cumulative counters cover closed operation/status outcomes, measured
token/cost coverage, tool calls and steps. Availability outcomes and request
latencies retain only a fixed 1000-entry numeric/status window; no request,
identity, thread, run, trace, action, error or content dimension is stored.

`GET /api/health/service-metrics` always returns HTTP 200 because an SLO breach
must not redefine liveness, readiness or a business result. The closed SLO uses
an operator-bounded minimum sample (maximum 1000), success-rate target and p95
latency target. Completed and confirmation-required results count as successful,
failed results count against availability, and cooperative/client cancellation
is excluded from its denominator. Before enough eligible/window observations,
all checks report `insufficient_data`; afterward each reports only `met` or
`breached`. This is per-replica telemetry for later rollout/incident automation,
not a distributed metrics store or an automatically accepted evaluation
baseline.

The fourth Slice 5 substage adds the frozen
`shopmind.release-operation-input.v1` and
`shopmind.release-operation-check.v1` contracts. A trusted release controller
captures the existing liveness, deployment-readiness, service-health/SLO and
governance-audit health snapshots. Seven ordered checks cover those four
boundaries, the selected coordination check, and rollback target/migration
proof. The evaluator performs no network, database, Redis, Agent or migration
operation and returns only closed decisions and reason/check IDs.

Deployment produces `continue_rollout`, `hold_rollout`, or `stop_rollout`;
rollback produces `execute_rollback`, `hold_rollback`, or `block_rollback`;
incident recovery produces `no_action`, `observe`, or `mitigate`. SLO warm-up
and audit pre-threshold warning wait for evidence, while liveness/readiness/
coordination failure, SLO breach or audit degradation fails the active
boundary. Rollback fails closed unless the exact target is verified and schema
compatibility is explicitly attested. It never treats a destructive Alembic
downgrade as an automatic recovery step.

`scripts/check_release_operations.py` consumes a captured typed envelope and
emits a sanitized artifact. The standalone
`shopmind.release-operations-eval.v1` CI gate covers seven deterministic
ready/warm-up/blocked/rollback/incident trajectories with `42/42` checks.
It remains outside the accepted catalog until an explicit baseline review.
`docs/operations_runbook.md` defines the rollout, rollback and recovery
sequence without adding a remote deployment control plane.

The fifth Slice 5 substage adds the compact policy-preserving reference client
at `examples/shopmind_reference_client.py`. Its bounded synchronous HTTP
transport supports JSON chat, ordered SSE, registered-action confirm/cancel
with server-validated edits, owner memory inspection, and exact-owner run/trace
inspection. It rejects redirects, credential-bearing/query URLs, non-loopback
plain HTTP, oversized responses/events, out-of-order SSE and untyped response
payloads. The CLI cannot provide arbitrary authentication headers; production
identity remains the responsibility of the trusted ingress.

Run/trace inspection is exposed additively through
`POST /api/owner-data/runs/inspect`. Chat, confirm and SSE final results return
opaque `run_id`/`trace_id` only when `include_debug=true`. The inspection route
requires the normal authenticated owner binding and exactly one selector. Its
frozen `shopmind.owner-run-inspection.v1` projection contains only run status,
mode/operation, bounded usage, timestamps, pending-action correlation and up
to 100 client-visible event summaries. It excludes input/output text,
request/result/debug/error/metadata/tool records, idempotency keys, event
payloads and internal/audit events. Cross-owner and missing selectors fail
without revealing existence.

The first release-candidate rehearsal exported the current source without
`.git`, `.env`, artifacts, virtual environments, model caches, or pytest
caches. From that isolated export, the default suite passed `668/668`, combined
PostgreSQL/Redis integration passed `25/25`, PostgreSQL and V3 handoff smoke
passed at migration `0007_governance_audit`, the single Alembic head and linear
revision history were verified, production preflight passed `6/6`, the catalog
passed `8/8` suites and `488/488` checks with `48/48` baseline comparisons, and
release operations passed `7/7` cases and `42/42` checks. This proves the source
does not depend on the original worktree's ignored caches or copied secrets.
At the time, that rehearsal did **not** satisfy the clean-checkout exit
criterion because Git HEAD was still the V3 release and V4-V6 existed only in
the worktree. The source was subsequently materialized by explicit
authorization as immutable commit `908b918`; its fresh detached checkout passed
the same matrix and supplied the required provenance.

### V6 Exit Criteria

- Versioned offline evaluations cover every production Agent, policy boundary,
  multi-turn memory, sensitive action, retry, cancellation, and adapter mode.
- A regression command compares a candidate against an accepted baseline and
  fails CI on configured quality, safety, latency, or cost regressions.
- Multi-process admission, deduplication, and cache behavior is tested with the
  configured coordination backend; local fallback behavior is explicit.
- Authentication, authorization, PII redaction, audit, retention, and deletion
  paths have executable tests and operator documentation.
- Metrics, dashboards, alerts, SLOs, deployment, rollback, and incident checks
  exist for the reference deployment.
- The reference client demonstrates JSON chat, SSE, sensitive-action resume,
  memory inspection, and trace/run inspection without bypassing API policy.
- A clean checkout passes default CI, PostgreSQL integration, API smoke,
  evaluation gates, migration/rollback checks, and release documentation.

## Deliberate Non-Goals

- Full checkout, payment, fulfillment, inventory administration, and storefront
  UI are not required for the Agent Engineering objective.
- A process sandbox is unnecessary while Agents cannot execute arbitrary code.
- Remote A2A is not a reason to deploy every Agent independently.
- LLM routing cannot override deterministic capability or write policy.
- Infrastructure is added only when runtime behavior requires it.

## Immediate Next Release Work

There is no remaining V6 implementation slice. Optional next work requires
separate authorization and belongs to release operations:

1. review the V4-V6 candidate commits and
   `docs/v6_release_candidate_notes.md`;
2. push the branch and open/merge a pull request;
3. choose the next semantic version and create the release/tag;
4. deploy through the trusted platform using `docs/operations_runbook.md`.

## Rough Schedule

V1-V5 and all V6 slices (global Slices 37-41) are complete. Slice 4 closed with
its authenticated-principal, closed PII-safe
audit contract, owner-scoped persistence/retention, default-off emission, and
authenticated owner-data lifecycle, signed-ingress identity, and sanitized
audit-monitoring substages plus an explicitly accepted offline governance
lifecycle baseline. Slice 5's static production-configuration preflight, live
deployment-readiness, versioned service metrics/SLOs and executable
deployment/rollback/incident checks plus the compact reference client are
implemented. Immutable commit `908b918` then passed the clean committed-checkout
matrix, satisfying the final exit criterion. Any future version starts from a
new explicitly approved roadmap; release publishing is not an implementation
slice.
