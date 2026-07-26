# PR Checklist

Use this checklist before opening or merging changes into `main`.

## Required

- [ ] Run the default local regression suite:

  ```bash
  conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe -m pytest tests/config tests/db tests/repositories tests/scripts tests/tools tests/api tests/agents tests/runtime tests/security tests/governance tests/docs tests/evaluation tests/integration
  ```

- [ ] Confirm `git status --short --branch` only shows intentional changes.
- [ ] Update README or docs when commands, environment variables, schemas, workflows, or developer setup steps change.
- [ ] Keep local Python commands on the existing `pythonLearn` conda environment. Do not create a new Python environment and do not use `python`, `pytest`, or `uv run` directly.

## ShopMind V3 Router / Multi-Agent Changes

- [ ] If supervisor routing, multi-agent graph behavior, route eval cases, or router documentation changed, run the deterministic router eval:

  ```bash
  conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe evaluation/run_router_eval.py --router deterministic
  ```

- [ ] If LLM router fallback behavior or observability changed, run the no-model fallback check:

  ```bash
  conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe evaluation/run_router_eval.py --router llm-fallback
  ```

- [ ] Only run `evaluation/run_router_eval.py --router llm` when you intentionally want a real structured model call and have configured provider credentials.

## ShopMind V5 Planner Changes

- [ ] If planner contracts, validation, provider fallback, or plan policy changed, run the deterministic planner policy gate:

  ```bash
  conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe evaluation/run_planner_eval.py --output-json artifacts/v5-planner-policy/summary.json
  ```

- [ ] Keep `SHOPMIND_AGENT_PLANNER=deterministic` in default CI. Real structured planner calls belong in explicit experiments, not the policy gate.
- [ ] Confirm CI publishes the `v5-planner-policy-eval` JSON artifact.
- [ ] If graph fan-out/fan-in, plan execution, cancellation, or shared tool-budget behavior changed, run the deterministic trajectory replay:

  ```bash
  conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe evaluation/run_plan_trajectory_eval.py --output-json artifacts/v5-plan-trajectories/summary.json
  ```

- [ ] Confirm CI publishes the `v5-plan-trajectory-eval` JSON artifact separately from planner-policy results.
- [ ] If task identity, delegation guards, or `max_steps` handling changed, confirm the shared-step-budget trajectory fails before a third tool call with `plan.step_budget_exceeded`.

## ShopMind V5 Adapter Changes

- [ ] If `AgentAdapter`, transport failure mapping, or HTTP specialist behavior changed, run the model-independent equivalence gate:

  ```bash
  conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe evaluation/run_adapter_equivalence_eval.py --output-json artifacts/v5-adapter-equivalence/summary.json
  ```

- [ ] Confirm the default production Registry still selects policy-wrapped in-process adapters and no API field accepts a remote endpoint or credential.
- [ ] Confirm HTTP endpoints use a server-owned HTTPS host allowlist, redirects are rejected, timeout/response limits are bounded, and failures contain no URL, token, response body, or provider exception detail.
- [ ] Keep adapter evaluation network-free with `httpx.MockTransport`; an external specialist is never required by default CI.
- [ ] Confirm CI publishes the `v5-adapter-equivalence-eval` artifact separately from planner and trajectory results.

## ShopMind V5 Action Lifecycle Changes

- [ ] If action definitions, preparation, confirmation, cancellation, expiry or ownership rules changed, run:

  ```bash
  conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe evaluation/run_action_lifecycle_eval.py --output-json artifacts/v5-action-lifecycle/summary.json
  ```

- [ ] Confirm action type and handler selection come only from the persisted record and server Registry; API callers must not choose either.
- [ ] Verify add-to-cart and save-preference confirm/cancel paths, exact edit schemas, duplicate transition, expiry, cross-user/thread denial, fresh-session resume, idempotency replay and sanitized handler failure.
- [ ] Confirm edits cannot change product/action/owner/thread/risk/expiry/handler and cancellation rejects edit payloads.
- [ ] Confirm `action.prepared/resumed/edited/confirmed/cancelled/expired/failed` events use the Harness sequence and CI publishes `v5-action-lifecycle-eval`.

## ShopMind V6 Evaluation Catalog Changes

- [ ] If a cataloged evaluator, artifact schema, required category, threshold,
  or accepted count changes, run:

  ```bash
  conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe evaluation/run_catalog_eval.py --output-json artifacts/v6-evaluation-catalog/summary.json
  ```

- [ ] Keep catalog runner selection closed and server-owned; manifests must not
  import arbitrary callables, use absolute/parent-relative artifact paths, or
  silently omit per-Agent, router, answer, trajectory, multi-turn, memory,
  safety, latency, token, or cost coverage.
- [ ] Treat `evaluation/baselines/v6_slice1_accepted.json` as reviewed policy.
  Candidate runs and CI must never overwrite or auto-accept it.
- [ ] Confirm CI retains each V5 artifact and separately publishes
  `v6-evaluation-catalog-regression` with both readable and JSON results.
- [ ] Keep the catalog gate model-, network-, credential-, PostgreSQL-, and
  LangSmith-independent.

## ShopMind V6 Governance And Owner-Data Changes

- [ ] Run `tests/security`, `tests/governance`, `tests/api/test_owner_data.py`
  and real PostgreSQL integration when identity, audit, retention or owner-data
  behavior changes.
- [ ] If `signed_header` identity or coordination changes, verify the four fixed
  headers, bounded timestamp/nonce/HMAC validation, stable 401/403 responses,
  secret-safe repr/response/audit behavior, and first-accept/second-reject
  replay across two real Redis clients.
- [ ] Keep `development_payload` as the compatibility default. Request bodies
  must not select identity providers, roles, scopes, secrets or remote
  endpoints.
- [ ] Verify every owner-data route binds authentication before storage access,
  rejects cross-owner requests, and keeps body schemas extra-forbidden.
- [ ] If owner run inspection changes, verify exactly one run/trace selector,
  exact-owner lookup, indistinguishable missing/cross-owner 404, bounded ordered
  client-event summaries, and exclusion of content, request/result JSON,
  payloads, debug/error/metadata, tools, idempotency and internal/audit events.
- [ ] Verify full deletion requires a UUID request ID plus literal confirmation,
  deletes only ShopMind owner rows in one transaction, and leaves catalogs,
  inherited customer/orders and independently retained audit facts untouched.
- [ ] Confirm audit rows contain no raw subject, memory content, action payload,
  database exception or connection URL, and audit failure cannot rewrite a
  committed business/deletion outcome.
- [ ] If audit monitoring changes, verify exact counters under concurrency,
  threshold-crossing only once, persisted/duplicate recovery, and that
  monitoring failure cannot change emitter or business results.
- [ ] Verify `/api/health/governance-audit` stays HTTP 200, is documented as
  internal/per-replica, and contains no audit record, identity, fingerprint,
  request, credential, exception or connection detail.

## ShopMind V6 Release Operations Changes

- [ ] For final release-candidate validation, record an immutable reviewed
  commit SHA, require a fresh checkout with empty `git status --porcelain`
  before and after validation, and keep artifacts outside or ignored.
- [ ] Do not treat a copied source export as Git provenance. Never copy `.env`,
  virtual environments, model caches or pytest caches into a candidate.
- [ ] If readiness, coordination, service SLO, audit monitoring, rollout,
  rollback or incident decisions change, run:

  ```bash
  conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe evaluation/run_release_operations_eval.py --output-json artifacts/v6-release-operations/summary.json
  ```

- [ ] Confirm all seven release checks remain ordered and output only closed
  statuses/reasons/actions; never copy endpoint payloads, paths, identifiers,
  connection values or raw errors into the report.
- [ ] Confirm `insufficient_data` and audit `warning` hold/observe rather than
  pass, and SLO breach, audit degradation, unavailable liveness/readiness or
  unavailable coordination fail the active operation.
- [ ] Confirm rollback remains blocked unless the exact target is verified and
  schema compatibility is explicitly reviewed. Never automate destructive
  Alembic downgrade from this check.
- [ ] Confirm CI publishes `v6-release-operations` separately. Do not add it to
  the accepted catalog without explicit baseline review.
- [ ] If the reference client changes, run
  `tests/scripts/test_shopmind_reference_client.py`; keep remote HTTPS,
  redirect, timeout, JSON/SSE size and sequence bounds intact, and do not add
  caller-controlled identity/signing headers, policy, credentials or endpoints.

## PostgreSQL Changes

- [ ] If database schema or repository behavior changed, run the default tests above.
- [ ] If local PostgreSQL is available, run the smoke check:

  ```bash
  conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe scripts/smoke_postgres.py
  ```

- [ ] For real PostgreSQL integration tests, use an isolated test database and set `RUN_POSTGRES_INTEGRATION=1`.

## CI

- [ ] Confirm the GitHub Actions default CI passes.
- [ ] Run the manual PostgreSQL Integration workflow when database schema, repository behavior, pgvector documents, or PostgreSQL-backed API paths change.
- [ ] Keep true PostgreSQL integration out of default CI unless the workflow explicitly provisions an isolated PostgreSQL + pgvector service.
