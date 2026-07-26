# ShopMind Reference Deployment Operations

This runbook covers the V6 reference deployment checks. It does not introduce
a deployment platform, remote control plane, distributed metrics store, or
automatic database downgrade. Operators remain responsible for trusted proxy,
TLS, scheduler, backup, artifact-signing, and external metrics aggregation.

## Inputs And Safety Boundary

The release controller captures four existing per-replica boundaries:

- `GET /api/health` for liveness;
- `GET /api/health/readiness` for configuration, PostgreSQL, migration,
  coordination, and cleanup readiness;
- `GET /api/health/service-metrics` for the bounded service SLO;
- `GET /api/health/governance-audit` for audit-emission warning/alert state.

It places them in a frozen `shopmind.release-operation-input.v1` envelope. The
envelope selects exactly one operation: `deployment`, `rollback`, or
`incident`. It also normalizes a missing liveness response to
`liveness_status=unavailable`. Rollback additionally requires closed
`rollback_target_status` and `rollback_migration_status` attestations.

The evaluator does not make network calls, connect to PostgreSQL/Redis, invoke
an Agent, mutate storage, or execute Alembic. It validates every nested schema
and emits only `shopmind.release-operation-check.v1`: ordered check IDs, closed
status/reason values, counts, and a closed recommended action. It never echoes
endpoint bodies, file paths, identifiers, connection values, errors, or
deployment artifact names.

The seven checks are:

1. `health.liveness`
2. `readiness.deployment`
3. `coordination.backend`
4. `service.slo`
5. `governance.audit`
6. `rollback.target`
7. `rollback.migration`

The two rollback checks are `not_applicable` outside rollback. Missing
coordination evidence fails closed even when an aggregate readiness artifact is
otherwise syntactically valid.

## Running A Captured Check

Assemble the endpoint snapshots in a trusted release controller, not from an
API caller:

```json
{
  "schema_version": "shopmind.release-operation-input.v1",
  "operation": "deployment",
  "liveness_status": "ok",
  "readiness": "<captured shopmind.deployment-readiness.v1 object>",
  "service_health": "<captured shopmind.service-health.v1 object>",
  "governance_audit_health": "<captured shopmind.governance-audit-health.v1 object>",
  "rollback_target_status": "not_applicable",
  "rollback_migration_status": "not_applicable"
}
```

The quoted placeholders above document composition and are not a valid input
artifact. Pass the completed JSON file to:

```powershell
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe scripts\check_release_operations.py --input-json artifacts\v6-release-operations\input.json
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe scripts\check_release_operations.py --input-json artifacts\v6-release-operations\input.json --output-json artifacts\v6-release-operations\report.json
```

The command exits zero only for `deployment=ready`, `rollback=ready`, or
`incident=stable`. `hold`, `observe`, `blocked`, and `action_required` exit
non-zero so an unattended pipeline cannot silently advance.

## Deployment

1. Run `scripts/check_production_config.py` against the intended environment.
2. Apply forward migrations through the deployment platform's reviewed,
   backed-up migration job.
3. Verify the cleanup scheduler has committed a recent
   `shopmind.runtime-cleanup-evidence.v1` marker.
4. Require `/api/health/readiness` HTTP 200 before admitting a replica.
5. Admit bounded canary traffic and capture all four health boundaries from
   every replica.
6. Run the deployment release-operation check before increasing traffic.

`service.slo=insufficient_data` or audit `warning` produces `hold_rollout`;
collect more bounded canary observations or resolve the warning. A readiness,
coordination, liveness, audit-alert, or SLO failure produces `stop_rollout`.
Only a fully passed report produces `continue_rollout`.

## Rollback

Before constructing a rollback envelope:

- verify the exact rollback application artifact in the deployment platform;
- review whether that application can run against the current schema;
- set `rollback_target_status=verified` only after artifact verification;
- set `rollback_migration_status=compatible` only after schema compatibility
  review.

Unverified or incompatible migration state blocks automatic rollback. The
current `0007_governance_audit` downgrade drops audit persistence, so a routine
application rollback should normally leave the forward schema at the current
head when the previous application is schema-compatible. Do not run Alembic
downgrade against a shared or production database merely to satisfy this
check. A schema restore, if required, belongs in an isolated, backed-up,
explicitly approved recovery procedure.

After deploying the verified rollback target, require its liveness, readiness,
coordination, service SLO, and audit health snapshots to pass. `execute_rollback`
means the evidence is sufficient for the controller's rollback step; it does
not mutate the deployment itself.

## Incident Recovery

Run the `incident` operation over current replica snapshots:

- `stable/no_action`: every active boundary passes;
- `observe/observe`: only warm-up SLO data or a pre-threshold audit warning
  remains;
- `action_required/mitigate`: liveness, readiness, coordination, SLO, or audit
  alert state fails.

Drain a replica when readiness is blocked. Investigate the specific closed
check IDs without copying secrets or payloads into incident channels. Use the
rollback procedure only after target and migration evidence is verified.
Repeat the incident check after mitigation; recovery is complete only at
`stable`.

## Clean Release-Candidate Validation

A release proof starts from an immutable reviewed Git reference, not from a
copied dirty worktree. Record the exact commit SHA, create a fresh checkout or
worktree at that SHA, and require `git status --porcelain` to be empty before
running any command. Test artifacts must be ignored or written outside the
checkout; require clean status again after validation.

Run, in order:

1. the default model-independent test suite;
2. PostgreSQL-only and combined PostgreSQL/Redis integration;
3. read-only PostgreSQL smoke and V3 API handoff smoke;
4. `alembic heads` and `alembic history`, requiring one linear head;
5. production configuration preflight with a reviewed reference profile;
6. the closed V6 catalog and standalone release-operations gate;
7. documentation consistency and `git diff --check`.

Do not copy `.env` into the checkout. The CI/release controller injects required
database, Redis and identity values through its protected environment. Never
seed, rebuild the document index, run destructive bootstrap, or execute an
Alembic downgrade merely to complete this matrix. Rollback validation consists
of revision review and the fail-closed release-operations trajectories unless
an isolated, backed-up migration-recovery exercise is separately approved.

An export that excludes `.git`, `.env`, artifacts, virtual environments and
caches is a useful rehearsal for hidden local dependencies. It is not a clean
checkout and cannot establish source provenance. If the implementation exists
only as unstaged or untracked files, stop after the rehearsal and obtain
explicit authorization for a reviewed immutable reference before claiming the
V6 exit criterion.

The first completed V6 proof used immutable implementation commit
`908b91888795f4d3d35096d6daf0592c840acdc3`. Its fresh detached worktree passed
the full matrix listed above and remained clean afterward. See
`docs/v6_release_candidate_notes.md`. This validation does not authorize a
push, pull request, tag, release, or deployment.

## Deterministic CI Gate

The standalone model-, network-, credential-, PostgreSQL-, Redis-, and
LangSmith-independent gate covers ready, warm-up, blocked, verified rollback,
unverified rollback, stable incident, and escalated incident trajectories:

```powershell
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe evaluation\run_release_operations_eval.py --output-json artifacts\v6-release-operations\summary.json
```

CI uploads the `v6-release-operations` artifact. This standalone candidate gate
does not modify the accepted V6 catalog baseline; adding it to that catalog
requires an explicit baseline review.
