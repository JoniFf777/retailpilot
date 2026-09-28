import { afterEach, describe, expect, it } from "vitest";
import type {
  CatalogCategoryListResponse,
  CatalogProductListResponse,
  ChatResponse,
  CheckoutPreview,
  CreateOrderResponse,
  OrderListResponse,
  PaymentAttemptResponse,
  PendingActionTransitionResponse,
  PendingActionView,
  ShoppingTaskListResponse,
  ShoppingTaskSnapshot,
} from "../api/contracts";
import { DAG_TASK_ID } from "./fixtures/tasks";
import { DEMO_PRODUCTS } from "./fixtures/catalog";
import { installDemoTransport } from "./index";

async function postJson<T>(path: string, body: unknown, idempotencyKey?: string): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (idempotencyKey) headers["Idempotency-Key"] = idempotencyKey;
  const response = await fetch(path, { method: "POST", headers, body: JSON.stringify(body) });
  expect(response.ok).toBe(true);
  return (await response.json()) as T;
}

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
    const response = await fetch("/api/owner-data/inspect");
    expect(response.status).toBe(501);
    const body = (await response.json()) as { detail: string };
    expect(body.detail).toMatch(/no fixture/);
  });

  it("serves catalog categories, a category's product list, and one product's detail", async () => {
    uninstall = installDemoTransport();
    const categories = (await (
      await fetch("/api/catalog/categories")
    ).json()) as CatalogCategoryListResponse;
    expect(categories.items?.map((item) => item.code).sort()).toEqual(["laptop", "monitor"]);

    const products = (await (
      await fetch("/api/catalog/products?category=laptop&limit=24&offset=0")
    ).json()) as CatalogProductListResponse;
    expect(products.items).toHaveLength(3);

    const productCode = DEMO_PRODUCTS.laptop[0]!.product_code;
    const detailResponse = await fetch(`/api/catalog/products/${productCode}`);
    expect(detailResponse.status).toBe(200);
    const detail = (await detailResponse.json()) as { product_code: string };
    expect(detail.product_code).toBe(productCode);
  });

  it("answers a direct SKU-code chat question without a recommendation panel", async () => {
    uninstall = installDemoTransport();
    const productCode = DEMO_PRODUCTS.laptop[0]!.product_code;
    const response = await postJson<ChatResponse>("/api/chat", {
      message: `${productCode} 多少钱？`,
      thread_id: "thread-1",
    });
    expect(response.status).toBe("completed");
    expect(response.recommendation).toBeNull();
    expect(response.answer).toContain(DEMO_PRODUCTS.laptop[0]!.name);
  });

  it("routes a low-budget chat message to a no_match recommendation", async () => {
    uninstall = installDemoTransport();
    const response = await postJson<ChatResponse>("/api/chat", {
      message: "预算 1000 元以内的笔记本",
      thread_id: "thread-1",
    });
    expect(response.recommendation?.outcome).toBe("no_match");
    expect(response.recommendation?.recommendations ?? []).toHaveLength(0);
  });

  it("streams progress frames before a terminal run.result event for the same scenario as the JSON endpoint", async () => {
    uninstall = installDemoTransport();
    const response = await fetch("/api/chat/stream", {
      method: "POST",
      headers: { Accept: "text/event-stream", "Content-Type": "application/json" },
      body: JSON.stringify({ message: "预算 12000 元以内的开发笔记本", thread_id: "thread-1" }),
    });
    expect(response.status).toBe(200);
    const text = await response.text();
    expect(text).toContain("event: run.started");
    expect(text).toContain("event: run.result");
    const resultLine = text
      .split("\n")
      .find((line) => line.startsWith("data:") && line.includes('"run.result"'));
    const event = JSON.parse(resultLine!.slice("data:".length).trim()) as { payload: ChatResponse };
    expect(event.payload.recommendation?.outcome).toBe("recommended");
  });

  it("walks the full critical path offline: recommend, confirm into the cart, checkout, order, and mock payment", async () => {
    uninstall = installDemoTransport();
    const chat = await postJson<ChatResponse>("/api/chat", {
      message: "预算 12000 元以内，适合开发和出差的轻薄笔记本",
      thread_id: "thread-1",
    });
    const first = chat.recommendation!.recommendations![0]!;

    const pendingAction = await postJson<PendingActionView>("/api/pending-actions/add-to-cart", {
      sku_id: first.sku_id,
      quantity: 1,
      source_run_id: chat.recommendation_context!.source_run_id,
      thread_id: "thread-1",
    });
    const confirmed = await postJson<PendingActionTransitionResponse>(
      `/api/pending-actions/${pendingAction.pending_action_id}/confirm`,
      { expected_version: pendingAction.version, thread_id: "thread-1" },
    );
    expect(confirmed.cart_quantity).toBe(1);

    const cartResponse = await fetch("/api/cart");
    const cart = (await cartResponse.json()) as { item_count: number };
    expect(cart.item_count).toBe(1);

    const preview = await postJson<CheckoutPreview>("/api/checkout/preview", {});
    expect(preview.can_create_order).toBe(true);

    const created = await postJson<CreateOrderResponse>(
      "/api/orders",
      { checkout_token: preview.checkout_token },
      "order-key-1",
    );
    expect(created.order.status).toBe("pending_payment");

    const listResponse = await fetch("/api/orders");
    const list = (await listResponse.json()) as OrderListResponse;
    expect(list.items.some((item) => item.order_id === created.order.order_id)).toBe(true);

    const payment = await postJson<PaymentAttemptResponse>(
      `/api/orders/${created.order.order_id}/payments`,
      { provider: "mock", payment_method_ref: "demo" },
      "pay-key-1",
    );
    expect(payment.payment_attempt.status).toBe("succeeded");
    expect(payment.order.status).toBe("paid");
  });

  it("serves a run inspection and a ready readiness report", async () => {
    uninstall = installDemoTransport();
    const runResponse = await postJson<{ run_id: string; status: string }>(
      "/api/owner-data/runs/inspect",
      { user_id: "demo-user", run_id: "any-selector" },
    );
    expect(runResponse.status).toBe("completed");

    const readinessResponse = await fetch("/api/health/readiness");
    expect(readinessResponse.status).toBe(200);
    const readiness = (await readinessResponse.json()) as { status: string };
    expect(readiness.status).toBe("ready");
  });
});
