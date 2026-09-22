import type {
  ShoppingTaskActionPreviewResult,
  ShoppingTaskActionResolution,
  ShoppingTaskCommandResult,
  ShoppingTaskCreateResult,
  ShoppingTaskListItem,
  ShoppingTaskSnapshot,
  TaskBundleProposalView,
  TaskKind,
} from "../api/contracts";
import { DEMO_OWNER_ID, SCENARIO_TASKS, scenarioListItems } from "./fixtures/tasks";

/** Mirrors the status codes the real routes raise for the same conditions
 *  (app/api/routes/shopping_tasks.py), so demo mode's error handling (409 conflict
 *  refetch, ApiError display, ...) behaves the same as it would against a real backend. */
export class DemoHttpError extends Error {
  constructor(
    readonly status: number,
    detail: string,
  ) {
    super(detail);
  }
}

const TERMINAL_STATUSES = new Set(["succeeded", "failed", "cancelled", "expired"]);

type PendingAction = {
  action_id: string;
  task_id: string;
  action_type: "add_bundle_to_cart" | "save_after_sales_draft";
  action_version: number;
  status: "pending" | "confirmed" | "cancelled" | "expired";
  payload: Record<string, unknown>;
};

function clone<T>(value: T): T {
  return structuredClone(value);
}

function requireVersion(task: ShoppingTaskSnapshot, expectedVersion: number): void {
  if (task.version !== expectedVersion) throw new DemoHttpError(409, "task_version_conflict");
}

export class DemoTaskStore {
  private readonly tasks = new Map<string, ShoppingTaskSnapshot>();
  private readonly createdAt = new Map<string, string>();
  private readonly actions = new Map<string, PendingAction>();
  private nextActionSuffix = 1;

  constructor(seed: ShoppingTaskSnapshot[] = SCENARIO_TASKS) {
    const seededCreatedAt = new Map(
      scenarioListItems().map((item) => [item.task_id, item.created_at]),
    );
    for (const task of seed) {
      this.tasks.set(task.task_id, clone(task));
      this.createdAt.set(
        task.task_id,
        seededCreatedAt.get(task.task_id) ?? new Date().toISOString(),
      );
    }
  }

  list(): ShoppingTaskListItem[] {
    return Array.from(this.tasks.values()).map((task) => ({
      task_id: task.task_id,
      kind: task.kind,
      status: task.status,
      mode: task.mode,
      version: task.version,
      created_at: this.createdAt.get(task.task_id) ?? new Date().toISOString(),
    }));
  }

  get(taskId: string): ShoppingTaskSnapshot {
    const task = this.tasks.get(taskId);
    if (!task) throw new DemoHttpError(404, "Shopping task not found");
    return clone(task);
  }

  create(input: { kind: TaskKind; goal_text: string }): ShoppingTaskCreateResult {
    const taskId = crypto.randomUUID();
    const task: ShoppingTaskSnapshot = {
      task_id: taskId,
      owner_id: DEMO_OWNER_ID,
      kind: input.kind,
      status: "queued",
      mode: "offline",
      version: 1,
      goal: {
        schema_version: "goal-spec.v1",
        kind: input.kind,
        goal_text: input.goal_text,
        required_slots: [],
        hard_constraints: {},
        soft_requirements: {},
        locked_selections: {},
        excluded_skus: [],
        open_questions: [],
        facts: [],
        version: 1,
      },
      plan: null,
      steps: [],
      artifacts: [],
      output: null,
      pending_interaction: null,
      last_sequence: 0,
    };
    this.tasks.set(taskId, task);
    return { accepted: true, mode: "offline", status: "queued", task_id: taskId, version: 1 };
  }

  cancel(taskId: string, expectedVersion: number): ShoppingTaskCommandResult {
    const task = this.tasks.get(taskId);
    if (!task) throw new DemoHttpError(404, "Shopping task not found");
    requireVersion(task, expectedVersion);
    task.status = "cancelled";
    task.version += 1;
    return { task_id: taskId, status: task.status, version: task.version };
  }

  addInputs(taskId: string, expectedVersion: number): ShoppingTaskCommandResult {
    const task = this.tasks.get(taskId);
    if (!task) throw new DemoHttpError(404, "Shopping task not found");
    requireVersion(task, expectedVersion);
    if (TERMINAL_STATUSES.has(task.status)) {
      throw new DemoHttpError(409, "terminal_task_requires_new_parent_task");
    }
    task.status = "queued";
    task.pending_interaction = null;
    task.version += 1;
    return { task_id: taskId, status: task.status, version: task.version };
  }

  prepareAction(
    taskId: string,
    expectedVersion: number,
    actionType: "add_bundle_to_cart" | "save_after_sales_draft",
  ): ShoppingTaskActionPreviewResult {
    const task = this.tasks.get(taskId);
    if (!task) throw new DemoHttpError(404, "Shopping task not found");
    requireVersion(task, expectedVersion);
    if (task.status !== "succeeded" && task.status !== "awaiting_approval") {
      throw new DemoHttpError(409, "task_result_not_ready");
    }
    const actionId = `00000000-0000-4000-a000-${String(this.nextActionSuffix++).padStart(12, "0")}`;
    const action: PendingAction = {
      action_id: actionId,
      task_id: taskId,
      action_type: actionType,
      action_version: 1,
      status: "pending",
      payload: (task.output as Record<string, unknown> | null) ?? {},
    };
    this.actions.set(actionId, action);
    task.status = "awaiting_approval";
    task.version += 1;
    return {
      action_id: actionId,
      action_type: actionType,
      status: action.status,
      version: task.version,
      expires_at: new Date(Date.now() + 15 * 60_000).toISOString(),
      payload: action.payload,
    };
  }

  confirmAction(
    taskId: string,
    actionId: string,
    expectedVersion: number,
    confirmed: boolean,
  ): ShoppingTaskActionResolution {
    const task = this.tasks.get(taskId);
    if (!task) throw new DemoHttpError(404, "Shopping task not found");
    const action = this.actions.get(actionId);
    if (!action || action.task_id !== taskId) throw new DemoHttpError(404, "action_not_found");
    requireVersion(task, expectedVersion);
    if (action.status !== "pending") throw new DemoHttpError(410, "action_expired");
    action.status = confirmed ? "confirmed" : "cancelled";
    task.status = "succeeded";
    task.version += 1;
    const resolution: ShoppingTaskActionResolution = {
      schema_version: "shopmind.task-action-resolution.v1",
      task_id: taskId,
      action_id: actionId,
      action_version: action.action_version,
      status: action.status,
      side_effect: confirmed
        ? action.action_type === "add_bundle_to_cart"
          ? true
          : "local_draft_only"
        : false,
    };
    if (confirmed && action.action_type === "add_bundle_to_cart") {
      const bundle = action.payload.bundle_proposal as TaskBundleProposalView | undefined;
      resolution.cart_items = bundle?.options?.[0]?.items?.map((item) => item.sku_code ?? "") ?? [];
    }
    if (confirmed && action.action_type === "save_after_sales_draft") {
      resolution.draft_only = true;
    }
    return resolution;
  }
}
