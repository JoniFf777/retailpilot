# ShopMind Project Status

Snapshot date: 2026-08-11

Current closure state: Phase 1-6B-2 accepted/closed; Project Closure
implementation in progress; Inbox/Consumer deferred.

## Summary

ShopMind is a FastAPI and LangGraph shopping-decision backend with a released V3
public baseline and complete V4-V6 Agent Runtime, collaboration, evaluation,
governance and production-reference layers. V4 provides the Harness,
persistence, Memory/Context, SSE/runtime control and Tool Gateway. V5 provides
canonical planning, bounded specialist execution/replay, local/HTTP adapter
equivalence, deterministic retry trajectories and editable, restart-safe
generic HITL actions. V6 provides the closed evaluation catalog, deterministic
fault/restart replay, local/Redis coordination, authenticated-principal owner
binding, PII-safe audit/retention/deletion, production preflight/readiness/SLO
checks, release-operation gates and a public-API reference client.

Immutable implementation commit
`908b91888795f4d3d35096d6daf0592c840acdc3` passed the full, integration,
smoke, migration, production-preflight and evaluation matrix from a fresh
detached worktree without copied secrets, caches or virtual environments. Git
status remained clean before and after. All V5 exit conditions are satisfied.
All V6 implementation exit criteria are satisfied.

## Release Baseline

- Version/tag: `v3.0.0`.
- V3 release commit: `c995896`.
- Release: <https://github.com/JoniFf777/retailpilot/releases/tag/v3.0.0>
- V4-V6 implementation commit:
  `908b91888795f4d3d35096d6daf0592c840acdc3`, clean-checkout validated and
  merged into `main`; no newer formal release/tag has been created.
- Endpoints: `GET /api/health`, `POST /api/chat`,
  `POST /api/chat/confirm`.
- Release path: multi-agent mode with deterministic Supervisor routing.

## What Exists Today

### User Interfaces

- The repository now contains the real `frontend/` React/Vite application and
  a separate live Playwright gate; the normal mocked frontend suites remain
  available for development without a running Backend.
- `examples/shopmind_reference_client.py` remains the compact public-API reference client
  and command-line demonstration.
- The implementation plan remains at `docs/frontend_implementation_plan.md`; the
  current runnable setup is `docs/demo_runbook.md`.
- `docs/demo_runbook.md` is the current copyable Core Demo setup and browser
  path; it uses the explicit `offline-demo` profile.

### Agents

- A legacy V1 single Agent remains available for comparison.
- The V3 Supervisor routes to Product, RAG, and Preference read Agents.
- The Decision Agent combines structured summaries into the final answer.
- LLM routing is optional and has deterministic fallback.
- Routes, Agent steps, decisions, safety flags, and confirmation events can be
  exposed as stable debug metadata.

### Safety And HITL

- Per-Agent allowlists prevent read Agents from using write tools.
- Add-to-cart intent crosses a dedicated guarded handoff.
- Explicit product identity or valid same-thread candidate selection is required
  before creating a pending action.
- `/api/chat/confirm` is the only public cart mutation boundary.
- Pending actions support confirmation/cancellation and validate user ownership.
- Candidate contexts are PostgreSQL-backed, bounded, and expire after ten
  minutes.

### Data And Retrieval

- PostgreSQL stores business data, preferences, cart items, pending actions, and
  candidate contexts.
- V4.1 now adds internal runtime persistence models for conversation threads,
  conversation messages, agent runs, run events, conversation summaries, and
  idempotency records.
- V4.3 adds explicit owner/thread-scoped memory records and bounded context
  slices with provenance, priority, expiry, and token estimates.
- V6 Slice 4 adds `governance_audit_records` with no direct owner/thread/run/
  resource identifiers, an immutable append repository, exact-owner
  fingerprint inspection and independent expiry pruning.
- Additive authenticated owner-data endpoints expose a bounded inventory and
  memory records, replace an exact-owner memory, hard-delete one memory, or
  transactionally delete all ShopMind-owned personal runtime/business data.
  Catalog/documents and inherited customer/order seed data are outside that
  deletion boundary; fingerprint-only audit facts retain their own expiry.
- V4.5 adds the first centralized `ToolGateway` slice over the V3 allowlists,
  with structured argument, ownership, sensitive-policy, output-limit, and
  per-run budget checks.
- pgvector stores product and policy document chunks.
- SQLAlchemy repositories isolate persistence from tools.
- The ShopMind Alembic head is `0014_shopmind_outbox_events` (`0007_governance_audit`
  remains the pre-ShopMind baseline revision).
- Bootstrap, seed, index, PostgreSQL smoke, and combined V3 smoke scripts exist.

### API, CI, And Evaluation

- Pydantic schemas provide OpenAPI examples for chat, selection, confirmation,
  and cancellation.
- Internal V4.1 runtime contracts now map the current V3 API into
  `RunRequest`, `RunContext`, `RunResult`, `AgentEvent`, `ToolCallRecord`, and
  a shared error model.
- GitHub Actions runs default tests and PostgreSQL/API integration checks.
- Event health artifacts, metrics, job summaries, and PR comments come from
  deterministic samples.
- LangSmith dataset/evaluation CLIs cover the V3 write handoff.
- API identity is selected only by server configuration. The default
  `development_payload` adapter preserves V3 behavior; explicit
  `trusted_header` mode binds a fixed proxy-authenticated subject, while
  `signed_header` additionally verifies timestamp/nonce/HMAC credentials and
  one-time replay admission before Agent/stream/action execution. Both return
  stable 401/403 failures.
- `shopmind.governance-audit.v1` defines frozen fingerprint-only records for
  authentication, tool, action, memory and deletion decisions. Its metadata is
  an exact typed allowlist and cannot carry raw messages, credentials, URLs or
  arbitrary runtime payloads. The internal repository persists that exact
  contract, bounds owner-scoped inspection and hides expired records.

### V4-V6 Implementation Complete

- The runtime Harness records the current V3 `/api/chat` and
  `/api/chat/confirm` invocations without changing user-visible responses.
- Request policy and budget now flow into `RunContext`; retryable failures,
  deadlines, cancellation checks, step/tool-call budgets, structured control
  errors, and finalization events share one lifecycle.
- Server-owned settings now resolve retries and optional duration, step, tool,
  and prompt budgets for every API-originated run. Sensitive-tool policy stays
  deny-first and is enabled only for the confirmation operation.
- Completed idempotent requests replay their persisted result without invoking
  tools or appending messages; conflicting or in-progress keys are rejected
  before execution.
- Conversation, message, run, summary, event, and idempotency repositories now
  follow the existing SQLAlchemy session-backed repository style.
- Runtime retention now has a concrete cleanup path through
  `scripts/cleanup_runtime_persistence.py`, alongside the existing
  candidate-context cleanup script.
- Default local tests cover the new contracts, repositories, Harness, and V3
  backward-compatibility path.
- Current V4.1-V6 Slice 5 validation is `668 passed, 6 skipped`;
  reference-client/API/docs focused coverage is `58/58`. The two
  real Redis integration cases remain explicit opt-ins in
  the default suite.
- PostgreSQL integration passes `23/23`, including fresh-store restart,
  repository isolation and Harness governance emission assertions; combined
  PostgreSQL/Redis integration passes `25/25`. PostgreSQL smoke passed at
  migration `0014_shopmind_outbox_events`, and V3 API handoff smoke passed `3/3`.
- The exact immutable implementation commit `908b918` passed that matrix from a
  fresh detached worktree. Production preflight passed `6/6`, the V6 catalog
  passed `8/8` suites with `488/488` checks and `48/48` comparisons, release
  operations passed `7/7` cases with `42/42` checks, and Git status remained
  clean after validation.
- V4.2 intentionally does not include async graph execution, Redis, or remote
  A2A; V4.3 memory loading is limited to the explicit local records and
  conversation sources described above.
- V4.3 provides explicit memory record repositories and a deterministic context
  manager; automatic long-term memory extraction and compaction remain out of
  scope for this slice.
- V4.4 adds `/api/chat/stream` SSE over the ordered Harness event sequence and
  keeps `/api/chat` as the complete JSON compatibility path. The current bridge
  streams lifecycle events and a final `run.result`; token-level provider
  streaming and hard interruption remain future work.
- V4.4's second slice bounds each SSE event queue and applies local in-process
  admission control. A full limit returns HTTP 429, while queue pressure
  requests Harness cancellation without changing the V3 JSON path.
- V4.5's first slice routes the existing V3 permission wrapper through a
  centralized capability registry. Invalid arguments, cross-user/thread
  references, disallowed sensitive tools, and exhausted tool budgets fail before
  delegation; generic action types and OS sandboxing remain future work.
- V4.5's second slice adds typed action definitions, risk/preview/expiry fields,
  row-locked confirmation transitions, and user/thread checks for pending actions.
- V4.5's third slice routes `/api/chat/confirm` through the `confirmation_boundary`
  capability. Sensitive tools require the explicit approved runtime policy, and
  gateway-generated `ToolCallRecord` data is preserved by the Harness.
- V4.5's fourth slice routes actual V3 read-tool delegation through
  `ToolGateway.invoke`, so validation and execution no longer use separate paths;
  legacy tool arguments and public responses remain unchanged.
- V4.5's fifth slice binds a fresh `RunContext` to each V3 read graph invocation,
  enabling per-run ownership and tool-budget enforcement without shared mutable
  Agent state.
- V4.5's sixth slice carries read-tool gateway records into `RunResult` and emits
  ordered `tool.call.completed` audit events before terminal run events; public
  API responses remain unchanged.
- V4.5's seventh slice records failed tool attempts with safe error metadata,
  persists the failure record, and emits `tool.call.failed` before `run.failed`
  without exposing underlying tool exception text through public responses.
- V4.5's eighth slice routes pending-action confirmation/cancellation through a
  typed `ActionTransitionRequest`; the registry validates action identity and
  rejects duplicate action definitions before selecting the transition tool.
- V4.5's ninth slice validates action creation through the same registry before
  the V3 write handoff creates a pending action; rejected definitions stop
  safely without changing valid add-to-cart responses.
- V4.5's tenth slice routes `prepare_add_to_cart` through a dedicated gateway
  capability classified as `WRITE`; only confirm and cancel remain sensitive
  cart boundaries, and prepare audit records are persisted by the Harness.
- V4.5's eleventh slice adds cooperative gateway execution controls: cancelled
  or timed-out runs skip tool invocation with structured audit records, while
  per-capability duration overruns remain audit metadata after successful
  provider return.
- V4.5's twelfth slice rejects blank and duplicate action/tool capability
  definitions during registry construction as well as later registration, so
  policy entries cannot be silently overwritten.
- V4.5's thirteenth slice adds typed, capability-owned database resource policy
  to `ToolCallRecord` audit data. Current registered catalog/document/preference
  tools are database reads, while prepare/confirm/cancel cart operations are
  database writes. Future network tools must supply an HTTPS host allowlist.
- V4.5's fourteenth slice makes production Gateway construction strict against
  the explicit V3 capability policy manifest. A newly allowed tool without a
  declared side-effect, confirmation, and resource policy fails before it can
  enter the multi-agent, write-handoff, or confirmation path.
- V4.5's fifteenth slice declares allowed Agent ownership in the same manifest.
  Strict Gateway construction now rejects allowlist drift that assigns an
  otherwise valid tool to a different Agent.
- V4.5's sixteenth slice exposes the capability manifest as read-only and
  validates it directly against the production V3 allowlist, preventing runtime
  mutation and test-fixture drift.
- V4.5's seventeenth slice also freezes nested `ToolResourcePolicy` contracts,
  preventing mutation of database or future network access declarations through
  an otherwise read-only manifest entry.
- V4.5's eighteenth slice validates confirmation semantics during capability
  registration: sensitive writes require confirmation, and non-write tools
  cannot declare it.
- V4.5's nineteenth slice includes the confirmation requirement in structured
  tool-call records and Harness audit events for persistence, streaming, and
  evaluation consumers.
- V5's first slice adds typed `AgentTask`/`AgentResult` contracts and an
  `InProcessAgentAdapter` that verifies recipient and task-result identity
  before a local handler runs. No HTTP/A2A transport or parallel fan-out is
  introduced.
- V5's second slice routes the existing product specialist through a typed
  local adapter bridge. It preserves current V3 state updates, tool selection,
  route order, and public API behavior.
- V5's third slice routes the existing RAG specialist through the same local
  adapter boundary. Existing RAG filtering and graph updates remain intact, and
  retrieved citation document IDs become typed `AgentResult.evidence_references`.
- V5's fourth slice routes the existing preference specialist through the local
  adapter and preserves its exact task `user_id` when reading preferences. All
  current V3 read specialists now use typed local adapter bridges, while their
  graph route order and public API behavior remain unchanged.
- V5's fifth slice validates task parent/depth identity and applies a shared,
  thread-safe delegation budget guard before each local handler. The guard
  rejects over-depth tasks and over-limit children of the same parent; the
  current V3 graph still creates root tasks only and does not enable fan-out.
- V5's sixth slice carries RAG document evidence references through the graph
  and records a conservative product-document scope mismatch in the structured
  decision when their product IDs do not overlap. It is observability only and
  does not change the user response, routes, or write policy.
- V5's seventh slice adds typed evidence conflict/resolution contracts and
  resolves that mismatch fail closed: the Decision Agent excludes the
  mismatched RAG summary, preserves non-conflicting summaries and reference
  IDs, and asks the user to clarify the product model. Matching evidence keeps
  the existing combined-read behavior.
- V5's eighth slice adds typed plan/step contracts and a deterministic route-plan
  builder. Plans validate unique step IDs, dependency references, acyclic
  dependencies, and execution-mode parallelism. Current read steps are marked
  logically independent, but execution remains sequential with
  `max_parallelism=1` and the existing dispatcher stays authoritative.
- V5's ninth slice adds typed plan-step/plan result contracts and a local bounded
  executor. Parallel mode is disabled by default, limited to independent steps,
  and preserves plan order during fan-in while deduplicating evidence and
  aggregating usage. Step exceptions become sanitized runtime errors. The
  executor is not connected to the V3 graph or public configuration yet.
- V5's tenth slice adds server-owned parallel-read settings (default off, one to
  three workers), isolated per-step graph state, and deterministic fan-in state
  mapping. Settings flow into runtime policy metadata but remain inert because
  shared runtime/tool counters are not yet approved for concurrent mutation.
- V5's eleventh slice adds a private metadata lock and stable snapshots to each
  `RunContext`. Tool calls atomically reserve budget before execution and carry
  ordered `audit_sequence` values, preventing concurrent budget overruns, lost
  records, and completion-order audit drift.
- V5's twelfth slice connects the server-owned parallel-read feature gate to the
  graph. Explicitly enabled multi-route reads use isolated specialist state and
  deterministic typed fan-in; default, single-route, and write paths remain
  sequential. Equivalence, partial failure, atomic shared-budget, and
  pre-execution cancellation tests preserve the V3 API and safety behavior.
- V5's thirteenth slice binds local cancellation and event callbacks to
  `RunContext` without serializing them. Plan workers cancel queued steps before
  execution, emit atomically sequenced lifecycle events, and allow already
  running synchronous calls to finish. Cancelled-run finalization preserves
  their real completed/failed tool records and audit events.
- V5's fourteenth slice adds an injectable planner protocol and validates every
  provider proposal against a server-compiled canonical plan. Route/intent,
  step/dependency, run identity, execution-mode, or parallelism drift triggers
  sanitized deterministic fallback. Accepted proposals are recompiled rather
  than trusted. No production planner setting or model invocation exists yet.
- V5's fifteenth slice adds `SHOPMIND_AGENT_PLANNER=llm` as an explicit,
  default-deterministic switch for a lazy LangChain structured-output provider.
  Provider output still passes the canonical validator and fallback. Router and
  planner modes are independent, and empty/write plans skip model invocation.
  Default tests use fake structured models only.
- V5's sixteenth slice adds a local planner policy evaluation: 10 fixed
  accepted/adversarial/fallback/write-guard trajectories with 70 canonical
  checks. The text/JSON CLI is model- and LangSmith-independent, sanitizes
  provider failures, and currently passes `10/10` cases and `70/70` checks.
- V5's seventeenth slice makes the deterministic planner policy suite a default
  CI gate. CI pins deterministic planner mode, writes the readable result to the
  workflow summary, and uploads the full JSON as `v5-planner-policy-eval` even
  when the gate reports policy failures. No planner model or credential is used.
- V5's eighteenth slice adds six fixed graph trajectory replays with 72 checks
  across complete fan-out/fan-in, partial failure, atomic shared tool/step
  budgets, pre-execution cancellation, and cooperative queued-step cancellation. Replays
  exercise the production graph, adapters, Gateway, executor, and Decision
  boundary with fake tools only. Their normalized versioned result excludes
  thread order, generated IDs, and timing. Its original baseline passed `6/6`,
  `72/72`; the twenty-second slice extends this gate as described below.
  Parallel plan workers now receive independent copies of the parent execution
  context, preserving request-local context variables without sharing a mutable
  `Context`; this also keeps the replay's tracing-disabled boundary offline.
- V5's nineteenth slice makes graph trajectory replay a default CI gate. It
  publishes a readable workflow summary and uploads the versioned JSON as
  `v5-plan-trajectory-eval`, independently of the planner policy artifact. Both
  gates run with deterministic planning and without model or tracing traffic.
- SSE finalization now flushes every event delivery already accepted from the
  worker before enqueueing the final result/error or stream terminator. This
  closes a thread/event-loop race without changing bounded-buffer overflow
  cancellation or the V3 JSON endpoints.
- V5's twentieth slice atomically reserves local Agent task steps in the shared
  delegation guard before handlers run. Admissions are isolated by run/task ID,
  use the stricter server-trusted/task budget, and return the stable
  `plan.step_budget_exceeded` code before a denied task can invoke a tool. Plan
  step identity now propagates into typed tasks on sequential and parallel paths.
- V5's twenty-first slice adds non-negative cost to `RunUsage`, carries typed
  usage through sequential/parallel specialist state and deterministic fan-in,
  and persists the aggregate on `RunResult`. The shared guard atomically
  reconciles every completed invocation against the stricter server/task
  prompt, completion, total-token, and cost ceilings. Missing or incomplete
  measurement fails closed when a ceiling is configured; repeated execution is
  charged again and run accounting remains isolated. Default unset ceilings
  preserve V3 behavior.
- V5's twenty-second slice checks delegation deadline and run-duration budgets
  before local handlers and again after they return or raise. The earliest
  task/server deadline and stricter task/server duration are authoritative;
  stable plan errors use the timeout source and record admission versus
  reconciliation. Synchronous calls are not force-terminated. Two offline
  expired-time scenarios extend graph trajectory replay to `8/8` cases and
  `96/96` checks, both with zero specialist tool calls.
- V5's twenty-third slice adds a runtime-checkable `AgentAdapter` protocol and
  shared invocation boundary for recipient, result type, and task-ID
  validation. All three specialist graph bridges depend on this protocol while
  their production factories remain in-process. The conformance suite includes
  a structural protocol-only adapter and graph bridge; no remote transport,
  endpoint configuration, or A2A network behavior exists.
- V5's twenty-fourth slice adds an immutable exact-recipient adapter registry.
  It rejects duplicate, malformed, unknown, and non-Protocol registrations.
  The server-owned graph factory registers only the three current in-process
  specialists, all sharing one trusted delegation guard. Registry selection is
  not exposed through API input or configuration, and remote adapters remain
  unavailable in production.
- V5's twenty-fifth slice makes delegation policy transport-independent.
  `InProcessAgentAdapter` is now a local typed transport only, while
  `PolicyEnforcedAgentAdapter` applies the shared admission, time, usage, and
  result-validation lifecycle around any Protocol implementation. All three
  production factory entries use this decorator and the same trusted guard; a
  protocol-only transport test confirms budgets apply before transport calls.
- V5's twenty-sixth slice makes policy wrapping mandatory for production
  registration. The generic registry remains transport-neutral by default,
  while its explicit policy-required mode rejects bare transports at
  construction. The server-owned ShopMind factory always enables that mode and
  exposes it as read-only diagnostic state; contract tests cover the fail-closed
  boundary.
- V5's twenty-seventh slice sanitizes Registry/graph/Harness failures. Unknown
  executor text is no longer persisted, and adapter contract plus delegation
  budget failures receive stable typed mappings without changing Tool Gateway
  errors. Complete parallel-graph fault injection covers private transport
  exceptions and wrong task IDs; both retain successful fan-in and expose only
  `plan.step_failed`. Registry testing confirms timeout reconciliation still
  wins over a private transport exception.
- V5's twenty-eighth slice introduces `AgentTransportError` with three
  server-defined failure classes, internally derived safe messages/source, and
  a required boolean retriable flag. Harness retries consume this typed signal;
  plan results preserve its code/source/retriability without replaying parallel
  steps. Invalid arbitrary codes and non-boolean retry flags fail closed.
- V5's twenty-ninth slice adds frozen `AgentTaskRetryPolicy` and deterministic
  task idempotency keys. Only the Plan Executor may own a multi-attempt policy;
  task identity must remain stable, every attempt must be accounted, and unsafe
  combinations fail validation. All production specialist tasks receive the
  runtime-derived key but remain retry-disabled with one attempt. Replay awaits
  failed-attempt usage reconciliation.
- V5's thirtieth slice requires typed usage on every transport failure and
  reconciles it through the shared delegation guard before propagation. Plan
  fan-in and Harness retry/finalization aggregate failed and successful attempt
  usage without converting unknown metrics to zero. Failed usage that is
  missing or over budget blocks replay; production specialist replay remains
  disabled.
- V5's thirty-first slice carries one frozen server-owned retry policy from the
  runtime through canonical plan steps into generated tasks. Production remains
  disabled at one attempt by default; explicit configuration is capped at three
  attempts and permits only typed unavailable/timeout failures. The Plan
  Executor preserves task identity/idempotency, checks cancellation between
  attempts, and aggregates all measured usage. Planner proposals cannot widen
  this policy, and opt-in sequential plans use the same typed executor.
- V5's thirty-second slice adds frozen structured attempt-event payloads and
  emits ordered attempt/retry lifecycle events through the existing Harness
  sequence. The same events are persistable run events and streamable SSE
  events. Five deterministic transport fault scenarios cover retry
  scheduled/started, success after retry, exhausted attempts, non-retriable
  failure, usage-budget blocking, and cancellation before replay. The offline
  graph gate now passes `13/13` cases and `195/195` checks under the versioned
  `shopmind.plan-trajectory-eval.v2` artifact, while the default remains one
  specialist attempt.
- V5's thirty-third slice implements a bounded HTTPS `HttpAgentAdapter` with a
  fixed host allowlist, no redirects, typed wire schemas, identity propagation,
  response limits and sanitized transport failures. Its offline equivalence
  gate passes `5/5` cases and `24/24` checks without network access.
- V5's thirty-fourth slice lets server configuration select that transport for
  RAG only. It remains disabled by default, fails closed when endpoint policy is
  incomplete, and keeps the same policy wrapper, Supervisor and graph contract.
- V5's thirty-fifth slice resolves pending action type from persisted scope and
  dispatches registered add-to-cart or save-preference handlers through the
  same confirmation boundary. Preference preparation has no final side effect;
  confirm/cancel/expiry/duplicate/scope/failure paths emit ordered `action.*`
  events. The offline gate passes `7/7` cases and `28/28` checks.
- V5's thirty-sixth slice adds exact Registry-owned edit schemas and an optional
  `updated_arguments` confirmation field. Add-to-cart permits only positive
  integer quantity edits; save-preference permits only normalized type/value
  edits. The handler applies edits and confirmation under one row lock and
  transaction, while owner/thread/type/risk/expiry/handler remain server-owned.
  Persisted action IDs resume without graph memory and emit ordered
  `action.resumed/edited/confirmed` events. PostgreSQL proves edit-confirm,
  reject, expiry and idempotent replay across fresh sessions. The action gate is
  now `shopmind.action-lifecycle-eval.v2` at `10/10` cases and `60/60` checks.
- The V5 exit condition is satisfied: canonical planning, bounded parallel
  collaboration, evidence conflict handling, shared delegation budgets,
  equivalent local/HTTP specialist contracts and generalized HITL are all
  executable without changing Supervisor business logic or the V3 API.
- V6 Slice 1 adds a closed `shopmind.evaluation-catalog.v1` manifest over five
  server-registered deterministic suites and requires explicit coverage for ten
  dimensions: per-Agent, router, answer, trajectory, multi-turn, memory,
  safety, latency, token, and cost. The accepted baseline locks every suite's
  artifact schema and minimum case/check counts. The comparison fails closed
  on missing suites/categories, schema or count shrinkage, quality/safety
  decline, or increased latency/token/cost regression counts. It currently
  passes `5/5` suites, `45/45` cases, `356/356` suite checks, and `33/33`
  baseline checks. CI publishes readable and JSON results and never accepts a
  new baseline automatically.
- V6 Slice 2 adds terminal-only, owner/thread-scoped normalized trajectory
  snapshots over existing persisted runs/events, with contiguous sequence,
  trace/identity and terminal-status validation. Raw request, result, output,
  debug, tool and event payloads are hashed; a closed safe scalar event
  classification remains available for assertions.
- The required resilience suite covers provider fallback, Tool Gateway failure,
  transport retry success, cancellation before retry, idempotent replay after a
  fresh store, and action resume after a fresh store. It passes `6/6` cases and
  `72/72` checks. The expanded catalog passes `7/7` suites, `56/56` cases,
  `446/446` suite checks, and `43/43` baseline checks against the explicitly
  tracked Slice 3 baseline.
- Two PostgreSQL integration assertions add retry/idempotency and action resume
  replay through a newly created engine/session factory. The expanded
  integration suite passes `18/18`.
- V6 Slice 3's first substage defines PII-safe coordination inputs and typed
  admission, renewal, release, rate-limit, duplicate-claim and bounded-cache
  decisions. The local backend uses one lock, injectable monotonic time, TTL
  cleanup and explicit cardinality/value-size limits. It passes `8/8` focused
  contract tests; the complete runtime group now passes `166/166`.
- The second substage adds a server-owned factory and configuration contract.
  Local remains the default. Explicit Redis selection requires a secret URL,
  installed client and reachable service; configuration/connection failures
  are sanitized and fail closed. Unknown values preserve compatibility by
  normalizing to local.
- SSE admission now uses renewable opaque leases and token-specific release
  through the selected backend. Existing capacity exhaustion remains HTTP 429
  and stream event/result behavior is unchanged.
- The third substage adds versioned Redis same-slot keys and atomic Lua
  admission, rate-limit, deduplication and bounded TTL/LRU cache operations.
  Offline local/Redis equivalence passes `5/5` cases and `18/18` checks. The
  expanded catalog passes `7/7` suites, `56/56` cases, `446/446` suite checks
  and `43/43` accepted-baseline checks. The default-skipped two-client real
  Redis gate passed with concurrent atomic admission and server TTL/cache
  expiry; combined PostgreSQL/Redis integration passes `22/22`.
- V6 Slice 4's first substage adds `AuthenticatedPrincipal` and
  `IdentityBoundary`, with server-selected compatibility/trusted-header modes
  and pre-execution owner binding.
- The second substage adds `GovernanceAuditFactory` and the frozen
  `shopmind.governance-audit.v1` schema. Every direct identity is reduced to a
  domain-separated fingerprint, operation/decision/reason values are closed,
  and category-specific metadata rejects arbitrary fields. Typed converters
  cover current authentication, Tool Gateway, action, memory and deletion
  boundaries without adding a public API.
- The third substage adds `governance_audit_records` and an immutable repository.
  Exact owner fingerprints are mandatory for inspection, results are
  newest-first and capped, expired rows are hidden, and the existing runtime
  cleanup command prunes only audit rows past their independent retention.
- The fourth substage adds server-owned, default-off production emission.
  Identity allow/deny decisions and Harness-projected typed tool, closed action
  lifecycle and selected persisted-memory facts use independent best-effort
  transactions and deterministic IDs. Sanitized storage failure cannot change
  HTTP, Agent or action results.
- The fifth substage adds four authenticated owner-data lifecycle endpoints.
  Inspection is bounded to 100 memory records and returns fixed category
  counts. Correction and memory deletion require an exact owner match; full
  deletion additionally requires a UUID request and literal confirmation.
  One transaction deletes preferences, cart/pending/candidate state and all
  owner conversation/run/event/summary/idempotency/memory rows. PII-safe memory
  and deletion request/execute facts remain independently retained. Cross-owner,
  duplicate-by-effect, sanitized failure and real PostgreSQL trajectories are
  executable.
- The sixth substage adds server-selected `signed_header` identity. A
  short-lived versioned HMAC assertion covers the normalized subject, epoch
  timestamp and nonce. Invalid, expired, replayed and backend-unavailable
  assertions share one public 401 response; one-time claims use only
  fingerprints and are atomic across Redis clients. The default remains
  `development_payload`, and request bodies still cannot carry identity mode,
  roles, scopes or credentials.
- The seventh substage adds `shopmind.governance-audit-monitor.v1`. Exact
  process counters cover closed emitter outcomes and records without retaining
  audit facts or raw identity/payload data. Three consecutive failures activate
  a configurable sanitized alert, a successful/duplicate commit recovers it,
  and `/api/health/governance-audit` returns the process snapshot without
  changing liveness or business outcomes.
- The eighth substage adds `shopmind.governance-lifecycle-eval.v1` with signed
  identity replay/owner denial, memory inspection/correction/deletion, full
  owner deletion and duplicate-by-effect execution, audit alert/recovery, and
  immutable audit persistence/idempotency. It passes `5/5` cases and `42/42`
  checks. The explicitly tracked `shopmind-v6-slice4-accepted` baseline now
  closes `8/8` suites, `61/61` cases, `488/488` suite checks and `48/48`
  comparisons; CI runs and publishes the governance artifact before the catalog
  gate.
- V6 Slice 5's first substage adds `shopmind.production-preflight.v1`. Six
  static, closed checks cover identity, coordination topology, audit emission,
  RAG transport, retention cleanup and runtime bounds. Explicit production
  mode blocks application creation when any check fails; development remains
  the default and reports `not_applicable`. The CLI, internal health route and
  CI artifact contain no configuration values or raw exceptions.
- V6 Slice 5's second substage adds `shopmind.deployment-readiness.v1`. Five
  closed live checks combine static preflight state with PostgreSQL
  connectivity, exact migration head, selected local/Redis coordination and
  recent cleanup success evidence. Cleanup writes a minimal atomic
  `shopmind.runtime-cleanup-evidence.v1` marker only after commit. The health
  endpoint, CLI and PostgreSQL CI artifact use only closed reasons and never
  serialize dependency values, paths or raw errors.
- V6 Slice 5's third substage adds `shopmind.service-metrics.v1`,
  `shopmind.service-slo.v1` and `shopmind.service-health.v1`. The Harness
  observes every terminal chat/confirmation request once. Cumulative closed
  counters and a fixed 1000-entry outcome/latency window have no identity,
  request or payload labels. Configured minimum sample, success-rate and p95
  targets produce only `insufficient_data|met|breached`; the internal endpoint
  always returns HTTP 200 and cannot alter business or readiness outcomes.
- V6 Slice 5's fourth substage adds `shopmind.release-operation-input.v1` and
  `shopmind.release-operation-check.v1`. Seven ordered checks compose captured
  liveness, readiness, coordination, service-SLO, audit-monitor and rollback
  target/migration evidence without making network, database or migration
  calls. Deployment, rollback and incident modes emit only closed decisions.
  Unverified/incompatible rollback evidence fails closed. The standalone
  `shopmind.release-operations-eval.v1` gate passes `7/7` cases and `42/42`
  checks in CI without changing the accepted catalog baseline.
- V6 Slice 5's fifth substage adds
  `examples/shopmind_reference_client.py` for bounded JSON chat, ordered SSE,
  registered HITL resume, memory inspection and run/trace inspection through
  public APIs only. Additive debug responses expose opaque run/trace IDs.
  `shopmind.owner-run-inspection.v1` requires exact-owner authentication and
  returns only run status/usage/timestamps plus at most 100 client-visible
  event summaries; content, arbitrary payloads, errors, debug metadata,
  idempotency data and internal/audit events are excluded.

## V3 Validation Record

- Full local suite: `227 passed, 4 skipped`.
- Deterministic router: `7/7` exact matches.
- LLM fallback router: `7/7` exact matches.
- PostgreSQL integration: `12/12`.
- API handoff smoke: `3/3`.
- LangSmith experiment `shopmind-v3-handoff-ef66ba2f`: 2 root runs, 0 errors.
- LangSmith deterministic feedback: `6/6` scores at `1.0`.
- Evaluation-owned runtime rows cleaned to zero.

See `docs/v3_release_notes.md` for the immutable release record.

## Post-V6 Optional Scope

### Phase 4A Checkout/Order Backend (accepted/closed)

Phase 4A implements the isolated Checkout Preview and pending-payment Order
reservation backend. It currently exposes `POST /api/checkout/preview`,
`POST /api/orders`, `GET /api/orders`, `GET /api/orders/{order_id}`, and
`POST /api/orders/{order_id}/cancel`. The backend is implemented and accepted/
closed. Payment was not part of Phase 4A; automatic expiration,
shipping/address/tax, the Phase 4B frontend, Redis/RocketMQ, and Outbox/Inbox
remain outside that phase.

| Capability | V6 completed state | Optional follow-up |
| --- | --- | --- |
| Remote specialist | Default-off server-owned HTTP RAG transport, policy-required Registry selection and 5/5 equivalence gate | Add deployment/operational checks only where V6 production requirements need them; do not distribute every Agent |
| Generic HITL | Add-to-cart/save-preference prepare, edit, approve, reject, resume, expire and replay through exact registered schemas and persisted IDs | V5 target met; V6 adds catalog-level regression and governance coverage |
| Planner decomposition | Canonical deterministic/validated provider plans with bounded multi-step parallel execution | V5 target met; V6 catalogs per-Agent and trajectory quality baselines |
| Evidence conflicts | Typed provenance, product/document mismatch detection and fail-closed resolution | V5 target met; V6 versions broader evidence/safety datasets |
| Memory lifecycle | Explicit records, summaries, bounded context/cleanup, authenticated inspection, correction and hard deletion | Automatic extraction/compaction only after the new lifecycle is accepted into regression baselines |
| Streaming control | SSE lifecycle events, bounded buffers and cooperative cancellation | Provider token streaming and documented hard/soft cancellation boundaries where supported |
| Distributed operations | Local default plus explicit atomic Redis admission, rate limits, deduplication and bounded cache; static topology validation, live database/migration/coordination readiness and executable rollout/rollback/incident checks | Aggregate per-replica telemetry in the deployment platform; do not add distributed coordination without a concrete runtime need |
| Production governance | Server-owned development/trusted/signed identity boundary, authenticated owner binding, closed PII-safe audit/persistence/retention/default-off emission, audit alerts, owner-data lifecycle, accepted offline regression, production preflight/readiness, service SLOs, release-operation checks, policy-preserving reference client, and clean release validation | Publish and deploy only through an explicitly authorized release workflow |
| Evaluation platform | Closed ten-dimension catalog, eight deterministic suites, normalized restart/coordination/governance replay, accepted Slice 4 baseline CI comparison and standalone release-operations gate | Add the operations gate to the accepted catalog only after explicit baseline review |

Full payment/fulfillment/storefront commerce remains outside V6 scope;
Phase 4A adds the isolated Checkout Preview and pending-payment Order
reservation backend, and Phase 5A adds the isolated Mock Payment Attempt
backend with local finalization.

### Phase 5A Mock Payment Backend (accepted/closed)

Phase 5A now adds the isolated ShopMind Mock Payment Attempt backend. It exposes
`POST /api/orders/{order_id}/payments` and
`GET /api/orders/{order_id}/payments`, with owner-bound Order amount/currency,
required idempotency, provider-outcome persistence and local reservation
finalization. Successful payment moves an Order from `pending_payment` to
`paid` and consumes its active Reservations; declined or unknown payment keeps
the Order pending and Reservations active.

`0013_shopmind_payments` is implemented after `0012_shopmind_orders`. The
server-owned Mock Provider supports success, decline and unknown/reconciliation
test scenarios through dependency injection or test/development setup only;
the client cannot submit scenario, amount, currency or user identity fields.
Phase 5A is accepted and closed. Phase 5B frontend, real payment providers,
webhooks, refunds/chargebacks, and automatic reconciliation remain outside the
implemented backend scope.

### Phase 6A Transactional Outbox + RocketMQ (accepted/closed)

Phase 6A adds migration `0014_shopmind_outbox_events` and a separate
transactional Outbox model/repository. Order Create, Order Cancel, and
successful Payment finalization enqueue immutable versioned events in the same
PostgreSQL transaction as their business facts. Claims use short leases,
database time, `FOR UPDATE SKIP LOCKED`, per-order sequence blocking, CAS
completion, bounded retry/backoff, dead-letter state, and explicit operator
redrive.

The standalone publisher sends `shopmind.order.created.v1`,
`shopmind.order.cancelled.v1`, and `shopmind.payment.succeeded.v1` to
`shopmind-order-events-v1` with `message_group=order_id`, event-type tags, and
event-ID keys. The Apache RocketMQ Python SDK is worker-only and lazy-loaded;
development defaults keep publishing disabled. Phase 6A is accepted and closed;
the publisher remains an optional Advanced Reliability Demo. Consumer, Inbox,
deduplication consumer, webhook, automatic reconciliation worker and Redis
remain deferred.

### Phase 6B-1 Core Demo Packaging (accepted/closed)

The current main chain is packaged by `scripts/start_shopmind_demo.ps1` into
Prepare, Start and Verify stages. Prepare is idempotent and fail-closed for
loopback/marked demo databases; Start launches only Backend and Frontend; Verify
and `frontend/e2e/live-critical-path.spec.ts` exercise the real
Recommendation -> explicit SKU -> PendingAction -> Cart -> Checkout -> Order ->
Mock Payment path. PostgreSQL assertions cover paid Order, succeeded
PaymentAttempt, consumed Reservation, exact inventory deltas and exactly-one
versioned Order/Payment Outbox events. Core startup needs no LangSmith
credentials and no RocketMQ SDK/Broker/Publisher. Phase 6B-1 is accepted and
closed.

### Phase 6B-2 Minimal Observability (accepted/closed)

Phase 6B-2 adds bounded HTTP correlation through `X-Correlation-ID`, JSON
structured logs with safe allowlisted fields, and transition logs for Order,
Payment and Outbox state boundaries. Unexpected HTTP Order/Payment exceptions
use stable error codes, exception class names and generic safe messages; they
do not log original exception strings. It adds the read-only
`scripts/inspect_outbox.py --json` operational snapshot plus optional
`GET /api/health/outbox` reporting. Core readiness remains determined by
Backend/PostgreSQL/core dependencies: a disabled publisher, backlog or
dead-letter rows do not make the Order API unavailable, and readiness does not
perform a RocketMQ network check. Health uses capped counters only and does
not load recent Outbox rows or payloads. Phase 6B-2 is accepted and closed; it
does not add Prometheus/Grafana/ELK,
OpenTelemetry Collector, external tracing, a monitoring dashboard, new
transaction behavior or Inbox/Consumer.

## Current Risks

- Remote adapter endpoint trust, response-size and server credential policy are
  enforced; deployment-specific identity/mTLS and external monitoring remain
  operator responsibilities rather than incomplete V6 implementation.
- Synchronous providers and tools cannot be force-terminated once running;
  cancellation and timeouts are cooperative at current boundaries.
- Automatic memory extraction/compaction is intentionally absent, so persisted
  memory evolution still requires explicit writes and summaries.
- Tool Gateway resource declarations are application policy, not database-role,
  network, process or OS isolation.
- Local admission control does not coordinate multiple API processes; operators
  must explicitly configure Redis mode for that boundary.
- Governance emission remains intentionally default-off as an explicit
  operator opt-in even though its lifecycle suite is accepted. Metrics are
  process-local, so operators must scrape every replica. Signed ingress requires
  protected shared-secret distribution and Redis coordination when more than
  one API process accepts requests.
- Production preflight validates declared relationships only. The separate live
  readiness contract now proves PostgreSQL/selected Redis reachability, exact
  migration head and a recent committed cleanup marker. It cannot prove proxy
  header stripping, future scheduler execution, certificate identity or secret
  rotation; the release-operation check therefore consumes explicit
  deployment-controller evidence rather than claiming to prove those facts.
- Service metrics and their 1000-observation SLO window are process-local and
  reset on process restart. Operators must scrape every replica and aggregate
  externally; the JSON health surface is not a durable metrics warehouse.
- Rollback target verification and schema compatibility are trusted
  deployment-controller attestations. The check fails closed when either is
  unverified, but deliberately does not perform destructive Alembic downgrade
  or prove backup restoration.
- The reference client intentionally cannot inject trusted/signed identity
  headers. Production use must pass through the configured trusted ingress;
  the client is not an authentication credential generator.
- V4-V6 implementation commit `908b918` is clean-checkout validated but not yet
  pushed, reviewed through a PR, versioned, tagged, or published after
  `v3.0.0`. Those are explicit release actions, not remaining implementation.

## Next-Window Handoff

1. Read `AGENTS.md` and `.local/retailpilot-runbook.md`.
2. Check the worktree before touching files.
3. Run read-only PostgreSQL smoke; do not reseed by default.
4. No V6 implementation slice remains. See
   `docs/v6_release_candidate_notes.md` for the clean validation record.
5. Push, PR, semantic version selection, tagging, and deployment require
   separate explicit authorization; do not perform them as routine startup.

## Historical Documents

- `docs/v2_infra_upgrade_handoff.md` - completed V2 infrastructure.
- `docs/v3_multi_agent_handoff_summary.md` - chronological V3 implementation.
- `docs/v3_release_notes.md` - formal V3.0.0 release.
- `docs/v3_api_handoff_contract.md` - current V3 caller contract.
- `docs/v6_release_candidate_notes.md` - validated V4-V6 implementation record.

Historical files explain how V3 was built; the active roadmap is `PLAN.md`.

## Frontend Status (2026-07-26)

The ShopMind Web frontend has started in the isolated `frontend/` directory;
no frontend package, source, Vite configuration, or dependency directory was
added at the repository root. F0 is complete: the pinned React + TypeScript +
Vite scaffold has lint, typecheck, Vitest, build, and API contract verification
commands; a local `/api` proxy; browser-safe typed chat/confirm, owner-data,
health, run-inspection, and POST-SSE clients; and the first responsive route
shell with design tokens.

F0 validation passed on 2026-07-26: lint, typecheck, 4 frontend tests,
production build, and API contract verification. The backend remains unchanged
and the PostgreSQL smoke baseline remains green. F1 JSON chat is the next
frontend stage; V1-V6 backend release, tag, and deployment state is unchanged.

F1 JSON Chat MVP is now complete. The root workbench submits typed requests to
`POST /api/chat`, renders assistant replies and stable status fields, keeps an
opaque thread identifier in browser storage, exposes development identity input
only in Vite development mode, and includes accessible empty/loading/error/
retry states with mocked component/API coverage. F1 validation passed with
lint, typecheck, 6 frontend tests, and production build; the backend remains
unchanged. F2 ordered POST-SSE is the next frontend stage.

F2 ordered POST-SSE is now complete. The workbench defaults to the backend
`POST /api/chat/stream` contract, consumes ordered `AgentEvent` frames through
`fetch`/`ReadableStream`, de-duplicates sequence numbers, renders bounded
client-visible progress, supports AbortController cancellation, and preserves
the JSON path as an explicit fallback. F2 validation passed with lint,
typecheck, 10 frontend tests, and production build. The backend remains
unchanged; F3 HITL actions are next.
## Frontend F3 Status (2026-07-26)

F3 HITL Actions is now complete. `confirmation_required` responses open a
typed action drawer for add-to-cart and save-preference, with exact editable
schemas, explicit confirm/cancel controls, idempotent mutation headers,
submission locking, and sanitized failure handling. F3 validation passed with
lint, typecheck, 14 frontend tests, and production build. The frontend still
does not persist action payloads or identity secrets, and the backend remains
unchanged. F4 owner-data, memory, and run inspection are next.
## Frontend F4 Status (2026-07-26)

F4 owner-data, memory, and run inspection is now complete. The isolated
`frontend/` app provides `/privacy` for exact-owner inventory, bounded Memory
inspection, allowlisted correction, confirmed Memory deletion, and exact-phrase
full deletion. `/runs` supports run_id/trace_id inspection and renders only
payload-free run and ordered event facts. Chat, Privacy Center, and Run
Inspector share the same development identity context; production identity
remains ingress-owned and no browser signing secret is included.

F4 validation passed with clean lint, typecheck,
17 frontend tests, and production build. No backend files were modified.
F5.1 health/status is complete; browser-level E2E setup remains separate.
## Frontend F5.1 Status (2026-07-26)

The first F5 slice is complete. `/status` integrates the public liveness and
deployment-readiness endpoints, including the backend's sanitized readiness
`503` JSON response, and provides loading, error, retry, refresh, responsive,
and bounded check-list states. A local JavaScript/CSS bundle-budget command is
also available after build. F5.1 passed clean lint, typecheck, 18 frontend
tests, production build, and the bundle-budget check. Playwright browser E2E is
explicitly pending a separate runner/browser setup; no machine-level software
was installed. The backend remains unchanged.
## Frontend F5.2 Status (2026-07-26)

F5.2 adds project-local Playwright configuration and two mocked critical paths
for POST-SSE chat completion and blocked readiness rendering. Playwright lists
both tests, and Vitest now excludes the E2E directory. Lint, app typecheck, E2E
typecheck, 18 unit tests, production build, and bundle budget all pass. Actual
browser execution is pending the local Playwright Chromium binary; no global or
machine-level software was installed and the backend remains unchanged.
## Frontend F5.2 Verification (2026-07-27)

Chromium is now installed for the project-level Playwright runner. The Chat
critical path expectation was corrected to match the intended UX: after send,
the input is cleared and the empty send button is disabled. Both Playwright
critical paths pass (`2 passed`). The full frontend validation is clean:
lint, app typecheck, E2E typecheck, 18 unit tests, Playwright E2E, production
build, and bundle budget. F5.2 is complete; F6 release configuration remains
separate. The backend remains unchanged.

## Phase 1B-Frontend Acceptance Patch (2026-08-05)

The frontend recommendation acceptance patch is complete. The current message
scope supports comparison of up to four SKUs, including Alternative SKUs;
selection beyond four is rejected visibly. Comparison focus lifecycle,
structured outcomes, fixed projection-error copy, strict SSE terminal guards,
literal OpenAPI enums, and budget/currency display are covered by the current
tests. `npm run e2e:list` lists seven mocked scenarios, and `npm run e2e`
passes all seven browser scenarios.
