import { afterEach, describe, expect, it } from "vitest";
import type { ShoppingTaskListResponse, ShoppingTaskSnapshot } from "../api/contracts";
import { DAG_TASK_ID } from "./fixtures/tasks";
import { installDemoTransport } from "./index";

const BADGE_SELECTOR = "#retailpilot-demo-badge";

let uninstall: (() => void) | null = null;

afterEach(() => {
  uninstall?.();
  uninstall = null;
});

describe("installDemoTransport", () => {
  it("replaces and restores globalThis.fetch, and shows/hides the demo badge", () => {
    const originalFetch = globalThis.fetch;
    uninstall = installDemoTransport();
    expect(globalThis.fetch).not.toBe(originalFetch);
    expect(document.querySelector(BADGE_SELECTOR)).not.toBeNull();
    uninstall();
    uninstall = null;
    expect(globalThis.fetch).toBe(originalFetch);
    expect(document.querySelector(BADGE_SELECTOR)).toBeNull();
  });

  it("is idempotent: a second install call is a no-op and doesn't duplicate the badge", () => {
    uninstall = installDemoTransport();
    const demoFetch = globalThis.fetch;
    const second = installDemoTransport();
    expect(document.querySelectorAll(BADGE_SELECTOR)).toHaveLength(1);
    second(); // no-op cleanup from the second call must not tear down the real install
    expect(globalThis.fetch).toBe(demoFetch);
    expect(document.querySelector(BADGE_SELECTOR)).not.toBeNull();
  });

  it("serves the task list", async () => {
    uninstall = installDemoTransport();
    const response = await fetch("/api/shopping-tasks?user_id=demo-user");
    expect(response.status).toBe(200);
    const body = (await response.json()) as ShoppingTaskListResponse;
    expect(body.items).toHaveLength(3);
  });

  it("serves a task snapshot by id", async () => {
    uninstall = installDemoTransport();
    const response = await fetch(`/api/shopping-tasks/${DAG_TASK_ID}?user_id=demo-user`);
    expect(response.status).toBe(200);
    const body = (await response.json()) as ShoppingTaskSnapshot;
    expect(body.task_id).toBe(DAG_TASK_ID);
  });

  it("creates a task and makes it readable at its own url", async () => {
    uninstall = installDemoTransport();
    const createResponse = await fetch("/api/shopping-tasks", {
      method: "POST",
      body: JSON.stringify({ user_id: "demo-user", kind: "bundle_selection", goal_text: "新任务" }),
    });
    expect(createResponse.status).toBe(202);
    const created = (await createResponse.json()) as { task_id: string };
    const getResponse = await fetch(`/api/shopping-tasks/${created.task_id}?user_id=demo-user`);
    const task = (await getResponse.json()) as ShoppingTaskSnapshot;
    expect(task.goal.goal_text).toBe("新任务");
  });

  it("cancels a task and reports a 409 with a stale version", async () => {
    uninstall = installDemoTransport();
    const createResponse = await fetch("/api/shopping-tasks", {
      method: "POST",
      body: JSON.stringify({ user_id: "demo-user", kind: "bundle_selection", goal_text: "取消我" }),
    });
    const created = (await createResponse.json()) as { task_id: string; version: number };
    const staleCancel = await fetch(`/api/shopping-tasks/${created.task_id}/cancel`, {
      method: "POST",
      body: JSON.stringify({ user_id: "demo-user", expected_version: 99 }),
    });
    expect(staleCancel.status).toBe(409);
    const cancelResponse = await fetch(`/api/shopping-tasks/${created.task_id}/cancel`, {
      method: "POST",
      body: JSON.stringify({ user_id: "demo-user", expected_version: created.version }),
    });
    expect(cancelResponse.status).toBe(200);
    const result = (await cancelResponse.json()) as { status: string };
    expect(result.status).toBe("cancelled");
  });

  it("returns an empty event stream instead of erroring", async () => {
    uninstall = installDemoTransport();
    const response = await fetch(`/api/shopping-tasks/${DAG_TASK_ID}/events?after_sequence=0`, {
      headers: { Accept: "text/event-stream" },
    });
    expect(response.status).toBe(200);
    expect(await response.text()).toBe("");
  });

  it("returns a clearly-labeled 501 for endpoints demo mode doesn't fake yet, instead of hitting the network", async () => {
    uninstall = installDemoTransport();
    const response = await fetch("/api/catalog/categories");
    expect(response.status).toBe(501);
    const body = (await response.json()) as { detail: string };
    expect(body.detail).toMatch(/no fixture/);
  });
});
