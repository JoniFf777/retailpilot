import type {
  ShoppingTaskListItem,
  ShoppingTaskSnapshot,
  TaskArtifactView,
} from "../../api/contracts";
import { degradedEvidence, okEvidence } from "./evidence";

export const DEMO_OWNER_ID = "demo-user";

export const DAG_TASK_ID = "00000000-0000-4000-8000-000000000001";
export const REVISION_TASK_ID = "00000000-0000-4000-8000-000000000002";
export const DEGRADED_TASK_ID = "00000000-0000-4000-8000-000000000003";

function artifact(
  overrides: Partial<TaskArtifactView> & Pick<TaskArtifactView, "id" | "branch">,
): TaskArtifactView {
  return { kind: "task_result", status: "passed", payload: {}, ...overrides };
}

/** DAG scenario: a fan-out/fan-in plan (goal -> {candidates, evidence} -> bundle -> verify)
 *  with one step still `running`, so a DAG renderer has real parallel branches and mixed
 *  node states to lay out, not just a straight line. */
function dagTask(): ShoppingTaskSnapshot {
  const leaseUntil = new Date(Date.now() + 5 * 60_000).toISOString();
  return {
    task_id: DAG_TASK_ID,
    owner_id: DEMO_OWNER_ID,
    kind: "bundle_selection",
    status: "running",
    mode: "offline",
    version: 4,
    goal: {
      schema_version: "goal-spec.v1",
      kind: "bundle_selection",
      goal_text: "我想为办公场景选择笔记本、显示器和扩展坞，预算 12000 元以内",
      required_slots: ["budget"],
      hard_constraints: { budget_max: "12000" },
      soft_requirements: {},
      locked_selections: {},
      excluded_skus: [],
      open_questions: [],
      facts: [],
      version: 1,
    },
    plan: {
      schema_version: "plan-proposal.v1",
      revision: 1,
      mode: "offline",
      reason: "deterministic_offline_plan",
      fingerprint: "",
      steps: [
        {
          key: "goal",
          capability: "extract_goal",
          role: "coordinator",
          depends_on: [],
          output_kind: "goal_spec",
          read_only: true,
        },
        {
          key: "candidates",
          capability: "catalog_candidates",
          role: "catalog_analyst",
          depends_on: ["goal"],
          output_kind: "catalog_candidates",
          read_only: true,
        },
        {
          key: "evidence",
          capability: "retrieve_evidence",
          role: "evidence_researcher",
          depends_on: ["goal"],
          output_kind: "evidence_bundle",
          read_only: true,
        },
        {
          key: "bundle",
          capability: "solve_bundle",
          role: "catalog_analyst",
          depends_on: ["candidates", "evidence"],
          output_kind: "bundle_proposal",
          read_only: true,
        },
        {
          key: "verify",
          capability: "verify_result",
          role: "coordinator",
          depends_on: ["bundle"],
          output_kind: "verification_report",
          read_only: true,
        },
      ],
    },
    steps: [
      {
        key: "goal",
        plan_revision: 1,
        capability: "extract_goal",
        role: "coordinator",
        status: "completed",
        attempt_count: 1,
        has_lease: false,
      },
      {
        key: "candidates",
        plan_revision: 1,
        capability: "catalog_candidates",
        role: "catalog_analyst",
        status: "completed",
        attempt_count: 1,
        output_artifact_id: "00000000-0000-4000-9000-000000000011",
        has_lease: false,
      },
      {
        key: "evidence",
        plan_revision: 1,
        capability: "retrieve_evidence",
        role: "evidence_researcher",
        status: "completed",
        attempt_count: 1,
        output_artifact_id: "00000000-0000-4000-9000-000000000012",
        has_lease: false,
      },
      {
        key: "bundle",
        plan_revision: 1,
        capability: "solve_bundle",
        role: "catalog_analyst",
        status: "running",
        attempt_count: 1,
        has_lease: true,
        lease_until: leaseUntil,
      },
      {
        key: "verify",
        plan_revision: 1,
        capability: "verify_result",
        role: "coordinator",
        status: "pending",
        attempt_count: 0,
        has_lease: false,
      },
    ],
    artifacts: [
      artifact({
        id: "00000000-0000-4000-9000-000000000011",
        branch: "candidates",
        kind: "catalog_candidates",
        payload: { sku_codes: ["NB-OFFICE-14", "MON-27-QHD", "DOCK-USB4"] },
      }),
      artifact({
        id: "00000000-0000-4000-9000-000000000012",
        branch: "evidence",
        kind: "evidence",
        payload: okEvidence(["NB-OFFICE-14", "MON-27-QHD", "DOCK-USB4"]),
      }),
    ],
    output: null,
    pending_interaction: null,
    last_sequence: 6,
  };
}

/** Revision scenario: round 1's `diagnostic` step got superseded by a repaired plan
 *  (revision 2) after the user answered a follow-up question, while the untouched
 *  `goal`/`compat` steps from revision 1 stay put. Exercises the `${plan_revision}:${key}`
 *  key collision TaskDetailPage.tsx's own steps.map() comment calls out. */
function revisionTask(): ShoppingTaskSnapshot {
  return {
    task_id: REVISION_TASK_ID,
    owner_id: DEMO_OWNER_ID,
    kind: "compatibility_diagnosis",
    status: "waiting_input",
    mode: "offline",
    version: 5,
    goal: {
      schema_version: "goal-spec.v1",
      kind: "compatibility_diagnosis",
      goal_text: "笔记本外接双显示器后偶发黑屏，想确认是否兼容问题",
      required_slots: ["device", "symptom"],
      hard_constraints: {},
      soft_requirements: {},
      locked_selections: {},
      excluded_skus: [],
      open_questions: ["symptom"],
      facts: [],
      diagnosis_state: {
        round: 1,
        answered_check_ids: ["check-cable-and-power"],
        ruled_out: [],
        observations: [
          {
            check_id: "check-cable-and-power",
            observation: "已更换线缆，问题依旧",
            source: "user_reported",
          },
        ],
      },
      version: 2,
    },
    plan: {
      schema_version: "plan-proposal.v1",
      revision: 2,
      mode: "offline",
      reason: "user_inputs",
      fingerprint: "",
      steps: [
        {
          key: "goal",
          capability: "extract_goal",
          role: "coordinator",
          depends_on: [],
          output_kind: "goal_spec",
          read_only: true,
        },
        {
          key: "compat",
          capability: "lookup_compatibility",
          role: "catalog_analyst",
          depends_on: ["goal"],
          output_kind: "compatibility_check",
          read_only: true,
        },
        {
          key: "diagnostic",
          capability: "suggest_diagnostic_check",
          role: "evidence_researcher",
          depends_on: ["compat"],
          output_kind: "diagnostic_check",
          read_only: true,
        },
        {
          key: "verify",
          capability: "verify_result",
          role: "coordinator",
          depends_on: ["diagnostic"],
          output_kind: "verification_report",
          read_only: true,
        },
      ],
    },
    steps: [
      {
        key: "goal",
        plan_revision: 1,
        capability: "extract_goal",
        role: "coordinator",
        status: "completed",
        attempt_count: 1,
        has_lease: false,
      },
      {
        key: "compat",
        plan_revision: 1,
        capability: "lookup_compatibility",
        role: "catalog_analyst",
        status: "completed",
        attempt_count: 1,
        output_artifact_id: "00000000-0000-4000-9000-000000000021",
        has_lease: false,
      },
      {
        key: "diagnostic",
        plan_revision: 1,
        capability: "suggest_diagnostic_check",
        role: "evidence_researcher",
        status: "superseded",
        attempt_count: 1,
        output_artifact_id: "00000000-0000-4000-9000-000000000022",
        has_lease: false,
      },
      {
        key: "diagnostic",
        plan_revision: 2,
        capability: "suggest_diagnostic_check",
        role: "evidence_researcher",
        status: "completed",
        attempt_count: 1,
        output_artifact_id: "00000000-0000-4000-9000-000000000023",
        has_lease: false,
      },
      {
        key: "verify",
        plan_revision: 2,
        capability: "verify_result",
        role: "coordinator",
        status: "pending",
        attempt_count: 0,
        has_lease: false,
      },
    ],
    artifacts: [
      artifact({
        id: "00000000-0000-4000-9000-000000000021",
        branch: "compat",
        kind: "compatibility_check",
        payload: { outcome: "unresolved" },
      }),
      artifact({
        id: "00000000-0000-4000-9000-000000000022",
        branch: "diagnostic",
        kind: "diagnostic_check",
        status: "superseded",
        payload: { suggested_check: "check-cable-and-power", round: 0 },
      }),
      artifact({
        id: "00000000-0000-4000-9000-000000000023",
        branch: "diagnostic",
        kind: "diagnostic_check",
        payload: { suggested_check: "check-display-driver-version", round: 1 },
      }),
    ],
    output: null,
    pending_interaction: { kind: "diagnostic_question", check_id: "check-display-driver-version" },
    last_sequence: 9,
  };
}

/** Degraded scenario: the task still succeeds (a reviewer accepted a repairable result),
 *  but the evidence backing one SKU came back degraded — the artifact itself is `passed`
 *  (it was produced and accepted), while its payload's own `status` is `degraded`, and the
 *  verification report surfaces that as an issue. Also exercises the prepare/confirm action
 *  flow since `status: "succeeded"` makes TaskDetailPage's action button appear. */
function degradedTask(): ShoppingTaskSnapshot {
  return {
    task_id: DEGRADED_TASK_ID,
    owner_id: DEMO_OWNER_ID,
    kind: "bundle_selection",
    status: "succeeded",
    mode: "offline",
    version: 6,
    goal: {
      schema_version: "goal-spec.v1",
      kind: "bundle_selection",
      goal_text: "预算 8000 元内配一套视频剪辑用的笔记本和存储扩展方案",
      required_slots: ["budget"],
      hard_constraints: { budget_max: "8000" },
      soft_requirements: {},
      locked_selections: {},
      excluded_skus: [],
      open_questions: [],
      facts: [],
      version: 1,
    },
    plan: {
      schema_version: "plan-proposal.v1",
      revision: 1,
      mode: "offline",
      reason: "deterministic_offline_plan",
      fingerprint: "",
      steps: [
        {
          key: "goal",
          capability: "extract_goal",
          role: "coordinator",
          depends_on: [],
          output_kind: "goal_spec",
          read_only: true,
        },
        {
          key: "candidates",
          capability: "catalog_candidates",
          role: "catalog_analyst",
          depends_on: ["goal"],
          output_kind: "catalog_candidates",
          read_only: true,
        },
        {
          key: "evidence",
          capability: "retrieve_evidence",
          role: "evidence_researcher",
          depends_on: ["goal"],
          output_kind: "evidence_bundle",
          read_only: true,
        },
        {
          key: "bundle",
          capability: "solve_bundle",
          role: "catalog_analyst",
          depends_on: ["candidates", "evidence"],
          output_kind: "bundle_proposal",
          read_only: true,
        },
        {
          key: "verify",
          capability: "verify_result",
          role: "coordinator",
          depends_on: ["bundle"],
          output_kind: "verification_report",
          read_only: true,
        },
      ],
    },
    steps: [
      {
        key: "goal",
        plan_revision: 1,
        capability: "extract_goal",
        role: "coordinator",
        status: "completed",
        attempt_count: 1,
        has_lease: false,
      },
      {
        key: "candidates",
        plan_revision: 1,
        capability: "catalog_candidates",
        role: "catalog_analyst",
        status: "completed",
        attempt_count: 1,
        output_artifact_id: "00000000-0000-4000-9000-000000000031",
        has_lease: false,
      },
      {
        key: "evidence",
        plan_revision: 1,
        capability: "retrieve_evidence",
        role: "evidence_researcher",
        status: "completed",
        attempt_count: 1,
        output_artifact_id: "00000000-0000-4000-9000-000000000032",
        has_lease: false,
      },
      {
        key: "bundle",
        plan_revision: 1,
        capability: "solve_bundle",
        role: "catalog_analyst",
        status: "completed",
        attempt_count: 1,
        output_artifact_id: "00000000-0000-4000-9000-000000000033",
        has_lease: false,
      },
      {
        key: "verify",
        plan_revision: 1,
        capability: "verify_result",
        role: "coordinator",
        status: "completed",
        attempt_count: 2,
        has_lease: false,
      },
    ],
    artifacts: [
      artifact({
        id: "00000000-0000-4000-9000-000000000031",
        branch: "candidates",
        kind: "catalog_candidates",
        payload: { sku_codes: ["LT-CREATOR-14", "SSD-NVME-2T"] },
      }),
      artifact({
        id: "00000000-0000-4000-9000-000000000032",
        branch: "evidence",
        kind: "evidence",
        payload: degradedEvidence(["SSD-NVME-2T"]),
      }),
      artifact({
        id: "00000000-0000-4000-9000-000000000033",
        branch: "bundle",
        kind: "task_result",
        payload: { outcome: "recommended" },
      }),
    ],
    output: {
      bundle_proposal: {
        options: [
          {
            total: "7896.00",
            currency: "CNY",
            items: [
              { slot: "laptop", sku_code: "LT-CREATOR-14", price: "6499.00" },
              { slot: "storage", sku_code: "SSD-NVME-2T", price: "1397.00" },
            ],
          },
        ],
      },
      verification_report: {
        schema_version: "verification-report.v1",
        status: "repairable",
        rule_version: "shopping-rules.v1",
        reviewer_used: true,
        progress_fingerprint: "demo-degraded-evidence",
        issues: [
          {
            code: "evidence_degraded",
            message: "存储扩展位的官方兼容说明检索降级，已用目录内规格替代核实。",
            affected_steps: ["evidence"],
            affected_artifacts: ["00000000-0000-4000-9000-000000000032"],
            affected_skus: ["SSD-NVME-2T"],
          },
        ],
      },
    },
    pending_interaction: null,
    last_sequence: 9,
  };
}

export const SCENARIO_TASKS: ShoppingTaskSnapshot[] = [dagTask(), revisionTask(), degradedTask()];

export function scenarioListItems(): ShoppingTaskListItem[] {
  return SCENARIO_TASKS.map((task) => ({
    task_id: task.task_id,
    kind: task.kind,
    status: task.status,
    mode: task.mode,
    version: task.version,
    created_at: new Date(Date.now() - 30 * 60_000).toISOString(),
  }));
}
