# Development And Local Runtime

This tracked guide contains no real keys or private credentials. Machine facts
belong in `.local/retailpilot-runbook.md`, which Git ignores.

## Windows Environment

- Repository: `D:\python\retailpilot`
- Conda environment: `pythonLearn`
- Interpreter: `D:\DL\Anaconda3\envs\pythonLearn\python.exe`
- Shell: PowerShell

Every Python command uses:

```powershell
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe ...
```

Do not use raw `python`, raw `pytest`, or `uv run`.

## Environment File

Create `.env` only if absent:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

`.env` is ignored. Core variables:

```env
DATABASE_URL="postgresql+psycopg://..."
TEST_DATABASE_URL="postgresql+psycopg://..."
EMBEDDING_PROVIDER="huggingface"
VECTOR_DIMENSION="768"
SHOPMIND_AGENT_MODE="multi"
SHOPMIND_SUPERVISOR_ROUTER="deterministic"
```

Model calls require a matching provider key and `WORKSHOP_MODEL`. LangSmith
requires its API key, tracing flag, and project. It is optional for default tests
and deterministic smoke. Never print `.env`; inspect names or redact values.

## PostgreSQL

The Compose service provides PostgreSQL 16 plus pgvector on port `5432`:

```powershell
docker compose up -d postgres
docker compose ps postgres
docker compose logs postgres
```

Before starting it, check the local runbook and port. `.env` may use an existing
host service or differently named container, causing a Compose port conflict.

Safe checks:

```powershell
Test-NetConnection 127.0.0.1 -Port 5432
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe scripts\smoke_postgres.py
```

Runtime retention helpers:

```powershell
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe scripts\cleanup_candidate_contexts.py
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe scripts\cleanup_runtime_persistence.py
```

V4.1 sets default retention windows for runtime conversation threads/messages and
agent runs, plus shorter idempotency retention, so cleanup can delete expired
rows without affecting active V3 flows. The same command now prunes
fingerprint-only governance audit rows only after their independent explicit
expiry; it does not remove active audit facts when a runtime row is deleted.
When `SHOPMIND_RUNTIME_CLEANUP_EVIDENCE_PATH` is configured, the command also
atomically records a PII-free success timestamp after the cleanup transaction
commits. Production readiness treats that marker as proof of recent execution.

Smoke masks the password and verifies database identity, migration, seed counts,
pgvector documents, and repository searches.

## Setup Or Upgrade

Apply migrations without clearing seed data:

```powershell
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe -m alembic upgrade head
```

Inspect bootstrap without executing:

```powershell
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe scripts\bootstrap_postgres.py
```

First-time initialization or intentional reset:

```powershell
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe scripts\bootstrap_postgres.py --execute --confirm-clear
```

The last command clears/reloads seed data and documents. Use it only after
verifying an isolated development target. Normal startup does not require it.

| Item | Expected |
| --- | ---: |
| Alembic | `0007_governance_audit` |
| customers | 50 |
| products | 25 |
| orders | 250 |
| order_items | 439 |
| product documents | 298 |
| policy documents | 39 |

## Run API

```powershell
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe -m uvicorn app.main:app --reload
```

- Health: <http://127.0.0.1:8000/api/health>
- Governance audit operations:
  <http://127.0.0.1:8000/api/health/governance-audit>
- Production configuration preflight:
  <http://127.0.0.1:8000/api/health/preflight>
- Live deployment readiness:
  <http://127.0.0.1:8000/api/health/readiness>
- Service metrics and SLO:
  <http://127.0.0.1:8000/api/health/service-metrics>
- Streaming chat: `POST http://127.0.0.1:8000/api/chat/stream` (SSE)
- OpenAPI: <http://127.0.0.1:8000/docs>
- ReDoc: <http://127.0.0.1:8000/redoc>

V3 returns complete JSON through `/api/chat`; V4.4 also exposes event-level SSE
through `/api/chat/stream`.

The local SSE bridge uses a bounded queue and in-process admission control. Its
defaults can be tuned without exposing secrets:

```env
SHOPMIND_STREAM_MAX_CONCURRENCY="8"
SHOPMIND_STREAM_EVENT_BUFFER_SIZE="128"
SHOPMIND_STREAM_ADMISSION_LEASE_TTL_MS="30000"
SHOPMIND_STREAM_ADMISSION_RENEW_INTERVAL_MS="10000"
SHOPMIND_COORDINATION_BACKEND="local"
SHOPMIND_DEPLOYMENT_PROFILE="development"
SHOPMIND_DEPLOYMENT_REPLICAS="1"
SHOPMIND_TRUSTED_PROXY_AUTHENTICATION="false"
SHOPMIND_RUNTIME_CLEANUP_SCHEDULED="false"
# SHOPMIND_RUNTIME_CLEANUP_EVIDENCE_PATH="artifacts/runtime-cleanup-evidence.json"
SHOPMIND_RUNTIME_CLEANUP_EVIDENCE_MAX_AGE_SECONDS="90000"
SHOPMIND_SERVICE_SLO_MIN_RUNS="20"
SHOPMIND_SERVICE_SLO_SUCCESS_RATE_TARGET="0.99"
SHOPMIND_SERVICE_SLO_P95_LATENCY_MS="5000"
SHOPMIND_IDENTITY_PROVIDER="development_payload"
# SHOPMIND_IDENTITY_SIGNING_SECRET="replace-with-at-least-32-random-characters"
SHOPMIND_IDENTITY_SIGNATURE_MAX_AGE_SECONDS="60"
SHOPMIND_IDENTITY_SIGNATURE_CLOCK_SKEW_SECONDS="5"
SHOPMIND_GOVERNANCE_AUDIT_ENABLED="false"
SHOPMIND_GOVERNANCE_AUDIT_ALERT_FAILURE_THRESHOLD="3"
SHOPMIND_RUNTIME_MAX_RETRIES="0"
SHOPMIND_AGENT_TASK_MAX_ATTEMPTS="1"
SHOPMIND_RAG_AGENT_TRANSPORT="in_process"
SHOPMIND_RUNTIME_MAX_DURATION_MS="0"
SHOPMIND_RUNTIME_MAX_STEPS="0"
SHOPMIND_RUNTIME_MAX_TOOL_CALLS="0"
SHOPMIND_RUNTIME_MAX_PROMPT_TOKENS="0"
SHOPMIND_RUNTIME_MAX_COMPLETION_TOKENS="0"
SHOPMIND_RUNTIME_MAX_TOTAL_TOKENS="0"
SHOPMIND_RUNTIME_MAX_COST_USD="0"
SHOPMIND_AGENT_PLANNER="deterministic"
SHOPMIND_PARALLEL_READ_ENABLED="false"
SHOPMIND_PARALLEL_READ_MAX_WORKERS="2"
```

Remote RAG is an explicit server deployment option, not a client feature. To
enable it, operators set `SHOPMIND_RAG_AGENT_TRANSPORT=http` together with a
fixed `SHOPMIND_RAG_AGENT_HTTP_ENDPOINT`, comma-separated
`SHOPMIND_RAG_AGENT_HTTP_ALLOWED_HOSTS`, and optionally the secret
`SHOPMIND_RAG_AGENT_HTTP_BEARER_TOKEN`. Timeout and decoded response bounds use
`SHOPMIND_RAG_AGENT_HTTP_TIMEOUT_SECONDS` (maximum 30) and
`SHOPMIND_RAG_AGENT_HTTP_MAX_RESPONSE_BYTES` (maximum 1048576). Do not record
real values in tracked files or logs. Missing endpoint/allowlist configuration
fails graph construction; the default needs none of these values.

Parallel-read settings are server-owned and the worker count is capped at three.
The feature is disabled by default. When explicitly enabled, only multi-route
independent reads use the bounded parallel graph path; single-route and write
flows remain sequential. Shared tool budgets and audit records are
concurrency-safe, and fan-in is deterministic in plan order.

`SHOPMIND_AGENT_TASK_MAX_ATTEMPTS` is separate from whole-Harness retries. It is
server-owned, defaults to one (disabled), and is capped at three. Values above
one replay only typed unavailable/timeout specialist failures under the same
task identity and idempotency key; protocol errors and untyped exceptions are
never replayed. Every attempt is reconciled against the shared usage/time
budgets, and cancellation is checked before another attempt starts.
Executor-owned attempts emit `plan.step.attempt.*` and `plan.step.retry.*`
events through the Harness sequence. Their payload includes plan/step/recipient
identity, attempt bounds, safe failure classification, retry decision, and
measured usage when available. The events are persisted with the run and are
available unchanged to SSE consumers.

Runtime usage ceilings are also server-owned and disabled when unset or zero.
When any token/cost ceiling is enabled, every delegated result must provide that
measurement (total tokens may be derived from complete input/output values).
Missing measurement fails closed rather than allowing a partial aggregate.
Token and cost limits are reconciled after each synchronous Agent result; they
do not interrupt an in-flight provider request.

`SHOPMIND_RUNTIME_MAX_DURATION_MS` applies to the whole Harness run, including
planning and delegated specialists. Each local Agent adapter checks the trusted
run start before invoking its handler and checks again when control returns.
An absolute request/budget deadline uses the earliest configured value. These
checks do not force-terminate synchronous Python or provider calls.

Streaming cancellation is cooperative. The Harness shares the stream's local
cancellation probe with the plan executor; steps that have not started are
cancelled before tool invocation. Synchronous calls already running finish and
retain their audit records. Lifecycle events use `plan.execution.*` and
`plan.step.*` names with the same monotonic sequence used by persisted events.

Planner mode accepts `deterministic` or `llm`; invalid values fall back to
`deterministic`. LLM mode lazily uses `WORKSHOP_MODEL` with structured output,
then validates the proposal against the server baseline. It is independent of
`SHOPMIND_SUPERVISOR_ROUTER`. Empty read plans and write handoff do not initialize
the planner model. Keep deterministic mode as the release/default test baseline.

Run the model-independent planner policy evaluation locally:

```powershell
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe evaluation\run_planner_eval.py
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe evaluation\run_planner_eval.py --json
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe evaluation\run_planner_eval.py --output-json artifacts\v5-planner-policy\summary.json
```

The fixed suite requires no database, LangSmith key, or model credentials. It
returns exit code `1` when any planner policy trajectory fails. The output file
is atomically replaced after the complete result is serialized. Default CI pins
`SHOPMIND_AGENT_PLANNER=deterministic`, uses this command as a gate, publishes
the text summary, and uploads `v5-planner-policy-eval` with the JSON result.

Run the model-independent compiled-graph trajectory replay evaluation:

```powershell
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe evaluation\run_plan_trajectory_eval.py
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe evaluation\run_plan_trajectory_eval.py --json
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe evaluation\run_plan_trajectory_eval.py --output-json artifacts\v5-plan-trajectories\summary.json
```

This suite uses deterministic routing and fake tools, but executes the real
compiled graph, typed adapters, Tool Gateway, bounded executor, cancellation,
and fan-in boundaries. It requires no model, credentials, or database. The
`shopmind.plan-trajectory-eval.v2` JSON normalizes concurrency into status/event
counts and ordering invariants so it can be compared across machines. Its 13
fixed cases include five deterministic retry transport faults covering success,
exhaustion, non-retriable failure, usage-budget blocking, and cancellation
before replay. Replay invocation explicitly
disables LangSmith tracing within its local context, even if application tracing
is enabled outside the command. The bounded executor propagates a separate copy
of that execution context to each worker thread.

Default CI runs this replay after the planner policy gate, appends its readable
result to the workflow summary, and uploads the versioned JSON as
`v5-plan-trajectory-eval`. Both gates use `always()` so each can retain its own
diagnostic artifact when the other gate or the default tests fail.

Run the transport and generic HITL contract gates:

```powershell
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe evaluation\run_adapter_equivalence_eval.py --output-json artifacts\v5-adapter-equivalence\summary.json
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe evaluation\run_action_lifecycle_eval.py --output-json artifacts\v5-action-lifecycle\summary.json
```

Both are network-, model-, credential-, LangSmith- and production-database-
independent. Adapter equivalence uses `httpx.MockTransport`; action lifecycle
uses an isolated in-memory repository and covers confirm, cancel, expiry,
cross-scope denial, duplicate transition and malformed payload failure. CI
publishes their JSON artifacts independently.

Run the V6 catalog and accepted-baseline regression gate:

```powershell
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe evaluation\run_catalog_eval.py
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe evaluation\run_catalog_eval.py --json
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe evaluation\run_catalog_eval.py --output-json artifacts\v6-evaluation-catalog\summary.json
```

Run the Slice 4 governance lifecycle gate independently:

```powershell
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe evaluation\run_governance_lifecycle_eval.py
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe evaluation\run_governance_lifecycle_eval.py --output-json artifacts\v6-governance-lifecycle\summary.json
```

Run the Slice 2 deterministic resilience/restart gate independently:

```powershell
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe evaluation\run_resilience_replay_eval.py
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe evaluation\run_resilience_replay_eval.py --output-json artifacts\v6-resilience-replay\summary.json
```

The six local scenarios use separate SQLite engines as a fresh-store boundary
and exercise the real planner fallback, Tool Gateway, Plan Executor, Harness,
idempotency and action repositories. They make no model, remote HTTP/A2A,
Redis, PostgreSQL or LangSmith call, and pass `72/72` stable checks. Raw fault,
request and output detail is not copied into the normalized trajectory.

The catalog command executes all eight closed, deterministic suite runners and
compares `61/61` accepted cases and `488/488` suite checks with the tracked
Slice 4 baseline. CI passes `--artifacts-root . --reuse-existing` after the V5,
resilience, coordination and governance gates, so their existing JSON is
validated and reused; a missing
artifact is regenerated
locally. The comparison exits non-zero for catalog/schema/count drift, suite
failures, quality or safety decline, or increased latency/token/cost regression
counts. It does not update the accepted baseline, initialize a model, make
network calls, or require PostgreSQL or LangSmith.

Run the V6 Slice 3 local coordination contract tests:

```powershell
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe -m pytest tests\runtime\test_coordination.py -q -p no:cacheprovider
```

The initial backend is intentionally local. It defines fingerprinted
admission/rate/dedup/cache
requests, renewable TTL leases, fixed windows, transient duplicate claims and
bounded JSON cache entries. The complete runtime group passes `166/166`. The
server-owned factory
reads `SHOPMIND_COORDINATION_BACKEND`; omitted/`local` is the default. Unknown
values normalize to local for compatibility. Explicit `redis` requires
`SHOPMIND_COORDINATION_REDIS_URL`, which is loaded as `SecretStr`, plus the
declared Redis client dependency and a reachable service. Atomic operations use
versioned same-slot keys; failures are sanitized and never fall back to local.

Run the offline coordination and optional real-service gates:

```powershell
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe evaluation\run_coordination_eval.py --output-json artifacts\v6-coordination-equivalence\summary.json
$env:RUN_REDIS_INTEGRATION="1"
$env:TEST_COORDINATION_REDIS_URL="<isolated server-owned test URL>"
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe -m pytest tests\integration\test_redis_coordination_integration.py -q -p no:cacheprovider
```

The offline gate passes `5/5` cases and `18/18` checks without a network call.
The integration test creates a unique versioned key scope and deletes only
that scope in cleanup. It has passed against real Redis with two clients,
concurrent admission and server TTL expiry. Do not point it at a shared
production Redis database.

The identity provider is server-owned. Keep
`SHOPMIND_IDENTITY_PROVIDER="development_payload"` for V3-compatible local
development. To test a trusted ingress boundary, set it to `trusted_header` and
send the fixed `X-ShopMind-Authenticated-User` header. Missing headers return
401; a different body `user_id` returns 403. A production proxy must remove
caller-supplied copies before injecting the authenticated subject. API JSON
never accepts roles, scopes, providers or credentials.

For a production-facing offline ingress adapter, select `signed_header` and
configure `SHOPMIND_IDENTITY_SIGNING_SECRET` with at least 32 random characters.
The trusted ingress must remove all caller-supplied identity headers and inject:

```text
X-ShopMind-Authenticated-User
X-ShopMind-Identity-Timestamp
X-ShopMind-Identity-Nonce
X-ShopMind-Identity-Signature
```

The timestamp is canonical decimal Unix seconds, the nonce is 16-128
URL-safe alphanumeric/underscore/hyphen characters, and the lowercase
hex signature is HMAC-SHA256 over:

```text
shopmind.identity-signature.v1\0<normalized-subject>\0<timestamp>\0<nonce>
```

Assertions default to a 60-second maximum age plus five seconds of future clock
skew; server settings cap those values at 300 and 30 seconds. Each assertion is
one-time. Local coordination protects one process; configure the existing
Redis coordination backend for atomic replay rejection across multiple API
processes. Never log the signing secret, nonce, signature or raw subject.
Missing/invalid/expired/replayed/backend-unavailable assertions return the same
401 challenge. This adapter does not call a remote IdP/JWKS endpoint.

V6 governance audit conversion uses the internal
`shopmind.governance-audit.v1` contract. It is not a logging instruction:
operators and application code must not print authentication subjects, request
messages, tool arguments/results, action previews, credentials, headers,
endpoints or connection URLs. `GovernanceAuditFactory` accepts current typed
boundaries and emits only domain-separated identity/resource fingerprints plus
category-specific allowlisted metadata. Arbitrary metadata is rejected, and
Tool Gateway result metadata is not copied.

Run its model- and database-independent contract tests with:

```powershell
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe -m pytest tests\security -q -p no:cacheprovider
```

These records are persisted internally in `governance_audit_records`; append is
immutable and owner-scoped inspection accepts only a domain-separated owner
fingerprint. The default retention is 90 days, result inspection is capped at
200, expired records are hidden, and `cleanup_runtime_persistence.py` enforces
their expiry. There is no public audit API yet, and production request/tool/
action/memory boundaries emit only when the server explicitly sets
`SHOPMIND_GOVERNANCE_AUDIT_ENABLED=true`. API JSON cannot enable it. Identity
allow/deny decisions, typed tool records, closed action lifecycle events and
persisted memory items selected into context are supported. Current request
content, arbitrary `AgentEvent.payload`, tool result metadata and memory content
are never copied.

Runtime persistence commits before a separate audit batch transaction.
Deterministic audit IDs make re-emission idempotent. Audit storage failure rolls
back only that batch, logs the closed `storage_unavailable` reason without an
exception/identifier, and cannot change 401/403, Agent, action or V3 response
semantics.

Every default emitter updates a shared process-local, PII-free metrics snapshot.
`SHOPMIND_GOVERNANCE_AUDIT_ALERT_FAILURE_THRESHOLD` defaults to three
consecutive failures and is capped at 100. Crossing it logs
`event=governance_audit_emission_alert state=active`; the next persisted or
duplicate commit logs `state=recovered`. Neither log contains an exception,
identifier, record or connection value.

Poll `GET /api/health/governance-audit` on each API replica. It returns HTTP 200
with `audit_enabled`, process status, alert state, cumulative emitter/record
counters and closed timestamps/reasons. Alert on `status=degraded` or
`monitor.alert_active=true`; treat `warning` as a pre-threshold signal. Do not
use this endpoint as a public audit query, and do not use it as a liveness
failure: business traffic remains valid when optional audit storage is down.
The governance lifecycle suite is explicitly accepted in the Slice 4 baseline,
but audit emission remains default-off and requires an operator opt-in.

Run the static Slice 5 production configuration preflight with the intended
deployment environment:

```powershell
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe scripts\check_production_config.py
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe scripts\check_production_config.py --json
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe scripts\check_production_config.py --output-json artifacts\v6-production-preflight\summary.json
```

The command returns zero only for an explicit, ready `production` profile.
Production requires either signed identity or `trusted_header` plus
`SHOPMIND_TRUSTED_PROXY_AUTHENTICATION=true`; more than one declared replica
requires configured Redis. It also requires audit emission, an operator
declaration that runtime cleanup is scheduled, and positive duration, step,
tool-call, total-token and cost limits. In-process RAG is valid; HTTP RAG must
use query-free HTTPS and the existing exact host allowlist.

The report is static and PII/secret-free. It does not connect to Redis,
PostgreSQL, the remote RAG endpoint or an IdP, and the proxy/scheduler flags are
deployment attestations rather than external proof. An explicitly selected
blocked production profile prevents FastAPI application creation. Development
remains the default and `/api/health/preflight` reports `not_applicable`.

Run the live readiness probe only after migrations and the configured cleanup
scheduler have produced a success marker:

```powershell
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe scripts\check_deployment_readiness.py
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe scripts\check_deployment_readiness.py --json
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe scripts\check_deployment_readiness.py --output-json artifacts\v6-deployment-readiness\summary.json
```

The command and `/api/health/readiness` return success only when all applicable
checks pass. In production, configure
`SHOPMIND_RUNTIME_CLEANUP_EVIDENCE_PATH` on storage shared by the scheduler and
API replica, set the bounded
`SHOPMIND_RUNTIME_CLEANUP_EVIDENCE_MAX_AGE_SECONDS` policy (default 90000,
maximum 604800), and run `cleanup_runtime_persistence.py` from the external
scheduler. Missing, malformed, future or stale markers fail closed. The marker
contains only schema, `succeeded`, and an aware UTC timestamp; readiness never
returns its path, a connection value, migration value or raw error. A 503 means
the instance must not receive new traffic; it is not the same as the
always-200 optional audit monitor.

Poll `GET /api/health/service-metrics` on every API replica. The default SLO
requires 20 eligible observations, a 0.99 successful terminal rate and p95
latency at or below 5000 ms. `SHOPMIND_SERVICE_SLO_MIN_RUNS` is capped at 1000,
matching the fixed rolling outcome/latency window;
`SHOPMIND_SERVICE_SLO_SUCCESS_RATE_TARGET` is bounded to `(0, 1]`, and
`SHOPMIND_SERVICE_SLO_P95_LATENCY_MS` is capped at 300000. A
`confirmation_required` result is successful service delivery, while a
cooperative/client cancellation is not an availability failure.

Treat `insufficient_data` as a rollout warm-up state and `breached` as an
operations alert input. The endpoint deliberately stays HTTP 200 and must not
replace `/api/health/readiness` for load-balancer admission. Counters and the
1000-entry window reset with each process and are not persisted; scrape every
replica and aggregate externally. The endpoint never returns a user/request/
thread/run/trace/action ID, content, error, tool/Agent name or arbitrary label.

For deployment, rollback, and incident automation, capture liveness,
deployment-readiness, service-health and governance-audit health snapshots in a
trusted controller and construct `shopmind.release-operation-input.v1`. Run:

```powershell
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe scripts\check_release_operations.py --input-json artifacts\v6-release-operations\input.json
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe scripts\check_release_operations.py --input-json artifacts\v6-release-operations\input.json --output-json artifacts\v6-release-operations\report.json
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe evaluation\run_release_operations_eval.py --output-json artifacts\v6-release-operations\summary.json
```

The evaluator is offline and value-free: it never fetches endpoints, connects
to PostgreSQL/Redis, mutates a deployment, invokes an Agent or runs Alembic.
Deployment returns `continue_rollout|hold_rollout|stop_rollout`; rollback
returns `execute_rollback|hold_rollback|block_rollback`; incident recovery
returns `no_action|observe|mitigate`. Rollback requires a separately verified
target and explicit migration-compatibility review. Never run a destructive
downgrade against a shared database simply to make a rollback check pass.
See `docs/operations_runbook.md` for the full capture, canary, rollback and
recovery sequence. The deterministic `7/7` case, `42/42` check CI gate remains
outside the accepted catalog pending explicit baseline review.

Run the persistence and retention tests with:

```powershell
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe -m pytest tests\repositories\test_governance_audit_repository.py tests\repositories\test_runtime_maintenance_repository.py -q -p no:cacheprovider
```

Run production projection/failure tests with:

```powershell
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe -m pytest tests\governance tests\api\test_identity_boundary.py tests\runtime\test_harness.py -q -p no:cacheprovider
```

Authenticated owner-data operations are additive:

| Endpoint | Required body facts | Effect |
| --- | --- | --- |
| `POST /api/owner-data/inspect` | `user_id`, optional `memory_limit` (1-100) | Fixed inventory counts plus bounded owner memory records |
| `POST /api/owner-data/runs/inspect` | `user_id`, exactly one `run_id`/`trace_id`, optional `event_limit` (1-100) | Exact-owner run metadata plus client-visible event summaries; no content or payloads |
| `POST /api/owner-data/memory/correct` | `user_id`, `memory_id`, replacement `content` | Replace one active/unexpired exact-owner memory and clear stale derived JSON |
| `POST /api/owner-data/memory/delete` | `user_id`, `memory_id` | Hard-delete one exact-owner memory |
| `POST /api/owner-data/delete` | `user_id`, UUID `deletion_request_id`, literal `confirmed=true` | Transactionally hard-delete ShopMind owner data |

All five operations require an authenticated binding. In compatibility
development mode the body owner creates the development principal; production
deployments must use `trusted_header` behind a protected proxy or the
`signed_header` adapter. Full deletion does
not delete product/document catalogs, inherited customer/order seed data, or
fingerprint-only governance audits. Repeating it after the data is gone returns
`already_deleted`. Storage failures return only HTTP 503
`Owner data storage unavailable.`.

The run-inspection response is frozen as
`shopmind.owner-run-inspection.v1`. It excludes request/result JSON,
input/output text, debug/error/metadata, tool records, idempotency facts, event
payloads and internal/audit events. Chat, confirm and SSE terminal responses
return its opaque run/trace selectors only when `include_debug=true`; the
selectors never authorize access by themselves.

Use the compact reference client against the local API:

```powershell
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe examples\shopmind_reference_client.py chat --message "推荐一款办公键盘" --user-id demo-user --thread-id demo-thread
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe examples\shopmind_reference_client.py stream --message "比较两款键盘" --user-id demo-user --thread-id demo-thread
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe examples\shopmind_reference_client.py confirm --user-id demo-user --thread-id demo-thread --pending-action-id PENDING_ID --approve --updated-arguments-json '{"quantity":2}'
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe examples\shopmind_reference_client.py memory --user-id demo-user --limit 20
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe examples\shopmind_reference_client.py run --user-id demo-user --run-id RUN_ID --event-limit 50
```

The client uses public APIs only. It defaults to loopback HTTP, requires HTTPS
for remote hosts, rejects credential-bearing/query URLs and redirects, and
bounds timeout/JSON/SSE sizes plus event ordering. It intentionally has no
arbitrary authentication-header or signing-secret option. Production traffic
must pass through the trusted ingress that owns identity injection.

Run the owner-data service/API tests with:

```powershell
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe -m pytest tests\governance\test_owner_data.py tests\api\test_owner_data.py -q -p no:cacheprovider
```

`/api/chat/stream` now acquires one lease at admission, renews it using the two
server-owned timing values, and releases the exact token when the generator
ends. Renewal must be shorter than TTL; invalid environment timing is
normalized, while invalid direct typed settings fail validation. Capacity
exhaustion and SSE output remain backward compatible.

When the local concurrency limit is full, `/api/chat/stream` returns HTTP 429.
When an individual client cannot drain its event buffer, the bridge requests
cancellation and waits for the Harness to finalize the run.
Worker-thread event deliveries that have already been accepted are flushed into
the asyncio queue before the final result/error and stream terminator. This
preserves lifecycle ordering without changing the non-blocking full-buffer
cancellation policy.

The runtime budget variables are server-owned defaults for every Harness run.
Use `0` to retain V3-compatible no-extra-limit behavior; a positive value enables
that limit. Only the confirmation operation may enable sensitive tools, so these
settings cannot make ordinary chat calls bypass the confirmation boundary.

`SHOPMIND_RUNTIME_MAX_STEPS` is enforced twice. The graph's shared delegation
guard atomically reserves each typed specialist task before its handler/tool can
run, using a server-trusted budget snapshot and a stricter task sub-budget when
present. Harness finalization still validates the complete Agent-step sequence,
including orchestration and Decision steps. A denied parallel step is reported
as `plan.step_budget_exceeded`; default `0`/unset behavior remains unlimited.

To activate runtime idempotency at the HTTP boundary, send a stable
`Idempotency-Key` header with `/api/chat`, `/api/chat/confirm`, or
`/api/chat/stream`. Reuse it only when retrying the identical user operation.

## Validation

```powershell
# Fast feedback
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe -m pytest tests\agents tests\api tests\docs

# Full suite
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe -m pytest

# Real PostgreSQL integration
$env:RUN_POSTGRES_INTEGRATION = "1"
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe -m pytest tests\integration
Remove-Item Env:RUN_POSTGRES_INTEGRATION

# PostgreSQL + API handoff smoke
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe scripts\smoke_v3_handoff.py --json
```

Handoff smoke uses dedicated users and cleans their runtime rows by default.

## LangSmith

LangSmith is optional unless the milestone requires cloud evaluation. V3
commands are in `docs/v3_release_notes.md` and evaluation CLI help. CLIs load
`.env` with `override=False`, so process variables win. Never include keys in
transcripts, screenshots, reports, commits, or PRs.

## New-Window Checklist

```powershell
Set-Location D:\python\retailpilot
git status --short --branch
Get-Content .local\retailpilot-runbook.md
Test-NetConnection 127.0.0.1 -Port 5432
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe scripts\smoke_postgres.py
```

Then read `PLAN.md`. Do not infer new work from historical V2/V3 handoffs.
Slice 36's editable, resumable add-to-cart/save-preference HITL lifecycle and
deterministic action gate are complete, satisfying the V5 exit condition. V6
Slices 1-2's versioned catalog, baseline and deterministic resilience/restart
implementation are complete. PostgreSQL integration passes `23/23` and V3
handoff passes `3/3`. V6 Slice 3 (global Slice 39) is complete: typed local and
atomic Redis coordination, server-owned backend selection, SSE renewable
leases, offline equivalence and real two-client integration all pass. V6 Slice
4 now has authenticated owner binding, closed PII-safe audit contracts,
PostgreSQL retention, default-off production emission, and authenticated
owner-data inspection/correction/deletion with deletion request/result facts.
The signed-ingress `IdentityBoundary` adapter is implemented with local/Redis
replay enforcement. Sanitized audit metrics/alerts, versioned service
metrics/SLOs and executable deployment/rollback/incident checks are
implemented. The compact public-API reference client and exact-owner run/trace
inspection are also implemented, completing Slice 5 functional scope. Continue
with clean release-candidate validation. The isolated source-export rehearsal
passes `668/668` default tests, `25/25` combined integration, PostgreSQL/V3
smoke, a single linear migration head, `6/6` production preflight, the complete
catalog and release-operations gate without copied Git metadata, `.env`, caches
or a virtual environment. This is not a clean-checkout proof: HEAD remains V3
`c995896`, and V4-V6 have no immutable Git reference under the current
no-stage/no-commit instruction. The static production configuration
preflight and live deployment readiness contracts are implemented. The
accepted governance gate is `5/5` cases
and `42/42` checks; the complete catalog is `8/8` suites, `61/61` cases,
`488/488` suite checks and `48/48` baseline checks.
Keep
`SHOPMIND_AGENT_TASK_MAX_ATTEMPTS=1` and the in-process adapter default unless a
focused test explicitly opts in; API callers must never supply remote endpoints
or credentials. Do not stage or restore the existing V4/V5 worktree changes.

## Troubleshooting

- **5432 occupied:** use the configured service; do not start a second database.
- **Migration mismatch:** run `alembic upgrade head`, then smoke again. V4.1
  adds runtime persistence tables for threads, messages, runs, summaries, and
  idempotency records; `0007_governance_audit` adds fingerprint-only audit
  persistence and retention indexes.
- **No documents:** verify embedding provider/dimension before intentional
  reindexing.
- **Provider error:** match `WORKSHOP_MODEL` to its key; deterministic tests
  should still work.
- **LangSmith unavailable:** continue local work unless cloud eval is required.
- **`rg` denied:** use `Get-ChildItem` and `Select-String`.
