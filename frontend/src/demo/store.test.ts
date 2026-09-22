import { describe, expect, it } from "vitest";
import { DAG_TASK_ID, DEGRADED_TASK_ID, REVISION_TASK_ID } from "./fixtures/tasks";
import { DemoHttpError, DemoTaskStore } from "./store";

describe("DemoTaskStore", () => {
  it("lists the three seeded scenarios", () => {
    const store = new DemoTaskStore();
    const items = store.list();
    expect(items.map((item) => item.task_id).sort()).toEqual(
      [DAG_TASK_ID, REVISION_TASK_ID, DEGRADED_TASK_ID].sort(),
    );
  });

  it("exposes a DAG scenario with parallel branches and one running step", () => {
    const store = new DemoTaskStore();
    const task = store.get(DAG_TASK_ID);
    expect(task.plan?.steps.map((step) => step.depends_on)).toContainEqual([
      "candidates",
      "evidence",
    ]);
    expect(task.steps?.filter((step) => step.status === "running")).toHaveLength(1);
  });

  it("exposes a revision scenario where the same step key spans two plan revisions", () => {
    const store = new DemoTaskStore();
    const task = store.get(REVISION_TASK_ID);
    const diagnosticSteps = task.steps?.filter((step) => step.key === "diagnostic") ?? [];
    expect(diagnosticSteps.map((step) => step.plan_revision).sort()).toEqual([1, 2]);
    expect(diagnosticSteps.find((step) => step.plan_revision === 1)?.status).toBe("superseded");
    expect(diagnosticSteps.find((step) => step.plan_revision === 2)?.status).toBe("completed");
  });

  it("exposes a degraded scenario with a repairable verification report", () => {
    const store = new DemoTaskStore();
    const task = store.get(DEGRADED_TASK_ID);
    expect(task.output?.verification_report?.status).toBe("repairable");
    expect(task.output?.bundle_proposal?.options).toHaveLength(1);
  });

  it("throws a 404 DemoHttpError for an unknown task id", () => {
    const store = new DemoTaskStore();
    expect(() => store.get("does-not-exist")).toThrow(DemoHttpError);
    try {
      store.get("does-not-exist");
      expect.unreachable();
    } catch (error) {
      expect(error).toBeInstanceOf(DemoHttpError);
      expect((error as DemoHttpError).status).toBe(404);
    }
  });

  it("creates a task and makes it immediately readable", () => {
    const store = new DemoTaskStore();
    const created = store.create({ kind: "bundle_selection", goal_text: "测试目标" });
    expect(created.status).toBe("queued");
    const task = store.get(created.task_id);
    expect(task.goal.goal_text).toBe("测试目标");
    expect(store.list().some((item) => item.task_id === created.task_id)).toBe(true);
  });

  it("cancels with the expected version and rejects a stale one", () => {
    const store = new DemoTaskStore();
    const created = store.create({ kind: "bundle_selection", goal_text: "测试目标" });
    expect(() => store.cancel(created.task_id, 99)).toThrow(DemoHttpError);
    const result = store.cancel(created.task_id, created.version);
    expect(result).toEqual({ task_id: created.task_id, status: "cancelled", version: 2 });
  });

  it("rejects addInputs on a terminal task", () => {
    const store = new DemoTaskStore();
    const created = store.create({ kind: "bundle_selection", goal_text: "测试目标" });
    store.cancel(created.task_id, created.version);
    expect(() => store.addInputs(created.task_id, 2)).toThrow(DemoHttpError);
  });

  it("runs prepareAction -> confirmAction end to end for a succeeded bundle task", () => {
    const store = new DemoTaskStore();
    const before = store.get(DEGRADED_TASK_ID);
    const prepared = store.prepareAction(DEGRADED_TASK_ID, before.version, "add_bundle_to_cart");
    expect(prepared.status).toBe("pending");
    const resolution = store.confirmAction(
      DEGRADED_TASK_ID,
      prepared.action_id,
      prepared.version,
      true,
    );
    expect(resolution.status).toBe("confirmed");
    expect(resolution.side_effect).toBe(true);
    expect(resolution.cart_items).toEqual(["LT-CREATOR-14", "SSD-NVME-2T"]);
    expect(store.get(DEGRADED_TASK_ID).status).toBe("succeeded");
  });

  it("rejects prepareAction when the task result isn't ready", () => {
    const store = new DemoTaskStore();
    const task = store.get(DAG_TASK_ID);
    expect(() => store.prepareAction(DAG_TASK_ID, task.version, "add_bundle_to_cart")).toThrow(
      DemoHttpError,
    );
  });
});
