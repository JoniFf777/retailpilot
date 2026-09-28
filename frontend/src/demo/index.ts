import type { TaskKind } from "../api/contracts";
import { DemoCommerceStore } from "./commerceStore";
import {
  ALL_DEMO_PRODUCTS,
  DEMO_CATEGORIES,
  DEMO_PRODUCTS,
  demoProductDetail,
  findDemoProductByCode,
} from "./fixtures/catalog";
import { buildChatResponse } from "./fixtures/chat-stream";
import { demoReadinessReport } from "./fixtures/readiness";
import { demoRunInspection } from "./fixtures/runs";
import { buildProgressEvents, buildTerminalEvent, selectScenario, sseFrame } from "./scenario";
import { DemoHttpError, DemoTaskStore } from "./store";

const BADGE_ID = "retailpilot-demo-badge";
const STREAM_FRAME_DELAY_MS = 320;

let installed = false;

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function emptyEventStream(): Response {
  return new Response("", { status: 200, headers: { "Content-Type": "text/event-stream" } });
}

function notImplemented(method: string, pathname: string): Response {
  return jsonResponse(
    { detail: `Demo transport has no fixture for ${method} ${pathname} yet.` },
    501,
  );
}

function requestUrl(input: RequestInfo | URL): URL {
  const raw = input instanceof Request ? input.url : String(input);
  return new URL(raw, location.origin);
}

function requestMethod(input: RequestInfo | URL, init: RequestInit | undefined): string {
  return (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
}

function requestBody(init: RequestInit | undefined): Record<string, unknown> {
  if (!init?.body || typeof init.body !== "string") return {};
  try {
    const parsed: unknown = JSON.parse(init.body);
    return parsed && typeof parsed === "object" ? (parsed as Record<string, unknown>) : {};
  } catch {
    return {};
  }
}

function idempotencyKeyOf(init: RequestInit | undefined): string {
  const headers = new Headers(init?.headers);
  return headers.get("Idempotency-Key") ?? crypto.randomUUID();
}

function injectDemoBadge(): () => void {
  if (document.getElementById(BADGE_ID)) return () => {};
  const badge = document.createElement("div");
  badge.id = BADGE_ID;
  badge.textContent = "演示数据 · 无真实后端";
  Object.assign(badge.style, {
    position: "fixed",
    right: "12px",
    bottom: "12px",
    zIndex: "2147483647",
    padding: "4px 10px",
    borderRadius: "999px",
    background: "#12241f",
    color: "#eef7f1",
    fontSize: "12px",
    fontFamily: "system-ui, sans-serif",
    boxShadow: "0 2px 8px rgba(0,0,0,0.25)",
    pointerEvents: "none",
  } satisfies Partial<CSSStyleDeclaration>);
  document.body.appendChild(badge);
  return () => badge.remove();
}

function routeShoppingTasks(
  store: DemoTaskStore,
  method: string,
  pathname: string,
  init: RequestInit | undefined,
): Response {
  const API_PREFIX = "/api/shopping-tasks";
  const segments = pathname.slice(API_PREFIX.length).split("/").filter(Boolean);
  try {
    if (segments.length === 0 && method === "GET") {
      return jsonResponse({ items: store.list(), limit: 50, offset: 0 });
    }
    if (segments.length === 0 && method === "POST") {
      const body = requestBody(init);
      return jsonResponse(
        store.create({ kind: body.kind as TaskKind, goal_text: String(body.goal_text ?? "") }),
        202,
      );
    }
    const [taskId, action, actionId, confirmSegment] = segments;
    if (segments.length === 1 && method === "GET") {
      return jsonResponse(store.get(taskId!));
    }
    if (segments.length === 2 && action === "events" && method === "GET") {
      store.get(taskId!);
      return emptyEventStream();
    }
    if (segments.length === 2 && action === "cancel" && method === "POST") {
      const body = requestBody(init);
      return jsonResponse(store.cancel(taskId!, Number(body.expected_version)));
    }
    if (segments.length === 2 && action === "inputs" && method === "POST") {
      const body = requestBody(init);
      return jsonResponse(store.addInputs(taskId!, Number(body.expected_version)));
    }
    if (segments.length === 2 && action === "actions" && method === "POST") {
      const body = requestBody(init);
      return jsonResponse(
        store.prepareAction(
          taskId!,
          Number(body.expected_version),
          body.action_type as "add_bundle_to_cart" | "save_after_sales_draft",
        ),
      );
    }
    if (
      segments.length === 4 &&
      action === "actions" &&
      confirmSegment === "confirm" &&
      method === "POST"
    ) {
      const body = requestBody(init);
      return jsonResponse(
        store.confirmAction(
          taskId!,
          actionId!,
          Number(body.expected_version),
          Boolean(body.confirmed),
        ),
      );
    }
  } catch (error) {
    if (error instanceof DemoHttpError)
      return jsonResponse({ detail: error.message }, error.status);
    throw error;
  }
  return notImplemented(method, pathname);
}

function routeCatalog(method: string, pathname: string, url: URL): Response {
  if (pathname === "/api/catalog/categories" && method === "GET") {
    return jsonResponse({ items: DEMO_CATEGORIES });
  }
  if (pathname === "/api/catalog/products" && method === "GET") {
    const categoryCode = url.searchParams.get("category") ?? "";
    const limit = Number(url.searchParams.get("limit") ?? 24);
    const offset = Number(url.searchParams.get("offset") ?? 0);
    const category = DEMO_CATEGORIES.find((item) => item.code === categoryCode);
    if (!category) return jsonResponse({ code: "unsupported_category", message: "未知分类" }, 404);
    const items = (DEMO_PRODUCTS as Record<string, typeof ALL_DEMO_PRODUCTS>)[categoryCode] ?? [];
    return jsonResponse({
      category,
      items: items.slice(offset, offset + limit),
      limit,
      offset,
      total: items.length,
    });
  }
  const productMatch = /^\/api\/catalog\/products\/([^/]+)$/.exec(pathname);
  if (productMatch && method === "GET") {
    const product = findDemoProductByCode(decodeURIComponent(productMatch[1]!));
    if (!product) return jsonResponse({ code: "catalog_not_found", message: "商品不存在" }, 404);
    return jsonResponse(demoProductDetail(product));
  }
  return notImplemented(method, pathname);
}

function routePendingActions(
  commerce: DemoCommerceStore,
  method: string,
  pathname: string,
  init: RequestInit | undefined,
): Response {
  try {
    if (pathname === "/api/pending-actions/add-to-cart" && method === "POST") {
      const body = requestBody(init);
      return jsonResponse(
        commerce.createAddToCartPendingAction({
          sku_id: String(body.sku_id),
          quantity: Number(body.quantity ?? 1),
          source_run_id: String(body.source_run_id ?? ""),
          thread_id: String(body.thread_id ?? ""),
          user_id: (body.user_id as string | undefined) ?? null,
        }),
        201,
      );
    }
    if (pathname === "/api/pending-actions/catalog-add-to-cart" && method === "POST") {
      const body = requestBody(init);
      return jsonResponse(
        commerce.createCatalogBrowsePendingAction({
          sku_id: String(body.sku_id),
          quantity: Number(body.quantity ?? 1),
          thread_id: String(body.thread_id ?? ""),
          user_id: (body.user_id as string | undefined) ?? null,
        }),
        201,
      );
    }
    const idMatch = /^\/api\/pending-actions\/([^/]+)(?:\/(confirm|cancel))?$/.exec(pathname);
    if (idMatch) {
      const [, pendingActionId, transition] = idMatch;
      if (!transition && method === "GET") {
        return jsonResponse(commerce.getPendingAction(pendingActionId!));
      }
      if (transition === "confirm" && method === "POST") {
        const body = requestBody(init);
        const updatedFields = body.updated_fields as Record<string, unknown> | undefined;
        const updatedQuantity =
          updatedFields && typeof updatedFields.quantity === "number"
            ? updatedFields.quantity
            : undefined;
        return jsonResponse(
          commerce.confirmPendingAction(
            pendingActionId!,
            Number(body.expected_version),
            updatedQuantity,
          ),
        );
      }
      if (transition === "cancel" && method === "POST") {
        const body = requestBody(init);
        return jsonResponse(
          commerce.cancelPendingAction(pendingActionId!, Number(body.expected_version)),
        );
      }
    }
  } catch (error) {
    if (error instanceof DemoHttpError)
      return jsonResponse({ detail: error.message }, error.status);
    throw error;
  }
  return notImplemented(method, pathname);
}

function routeCart(
  commerce: DemoCommerceStore,
  method: string,
  pathname: string,
  init: RequestInit | undefined,
): Response {
  try {
    if (pathname === "/api/cart" && method === "GET") return jsonResponse(commerce.getCart());
    if (pathname === "/api/cart" && method === "DELETE") {
      commerce.clearCart();
      return new Response(null, { status: 204 });
    }
    const itemMatch = /^\/api\/cart\/items\/([^/]+)$/.exec(pathname);
    if (itemMatch && method === "PATCH") {
      const body = requestBody(init);
      return jsonResponse(
        commerce.updateCartItem(
          itemMatch[1]!,
          Number(body.expected_version),
          Number(body.quantity),
        ),
      );
    }
    if (itemMatch && method === "DELETE") {
      commerce.deleteCartItem(itemMatch[1]!);
      return new Response(null, { status: 204 });
    }
  } catch (error) {
    if (error instanceof DemoHttpError)
      return jsonResponse({ detail: error.message }, error.status);
    throw error;
  }
  return notImplemented(method, pathname);
}

function routeCheckoutAndOrders(
  commerce: DemoCommerceStore,
  method: string,
  pathname: string,
  init: RequestInit | undefined,
): Response {
  try {
    if (pathname === "/api/checkout/preview" && method === "POST") {
      return jsonResponse(commerce.checkoutPreview());
    }
    if (pathname === "/api/orders" && method === "POST") {
      const body = requestBody(init);
      return jsonResponse(
        commerce.createOrder(String(body.checkout_token ?? ""), idempotencyKeyOf(init)),
        201,
      );
    }
    if (pathname === "/api/orders" && method === "GET") {
      return jsonResponse(commerce.listOrders());
    }
    const cancelMatch = /^\/api\/orders\/([^/]+)\/cancel$/.exec(pathname);
    if (cancelMatch && method === "POST") {
      return jsonResponse(commerce.cancelOrder(cancelMatch[1]!));
    }
    const paymentsMatch = /^\/api\/orders\/([^/]+)\/payments$/.exec(pathname);
    if (paymentsMatch && method === "POST") {
      return jsonResponse(commerce.createPayment(paymentsMatch[1]!, idempotencyKeyOf(init)), 201);
    }
    if (paymentsMatch && method === "GET") {
      return jsonResponse(commerce.listPayments(paymentsMatch[1]!));
    }
    const orderMatch = /^\/api\/orders\/([^/]+)$/.exec(pathname);
    if (orderMatch && method === "GET") {
      return jsonResponse(commerce.getOrder(orderMatch[1]!));
    }
  } catch (error) {
    if (error instanceof DemoHttpError)
      return jsonResponse({ detail: error.message }, error.status);
    throw error;
  }
  return notImplemented(method, pathname);
}

function chatResultFor(message: string, threadId: string, runId: string) {
  const scenario = selectScenario(message);
  if (scenario.kind === "sku_lookup") {
    return {
      answer: scenario.answer,
      status: "completed" as const,
      retry_state: "none" as const,
      thread_id: threadId,
      tool_calls: [],
      pending_action_id: null,
      projection_error: null,
      recommendation: null,
      recommendation_context: null,
    };
  }
  return buildChatResponse(scenario.result, threadId, runId);
}

function routeChat(method: string, pathname: string, init: RequestInit | undefined): Response {
  if (pathname === "/api/chat" && method === "POST") {
    const body = requestBody(init);
    const threadId = String(body.thread_id ?? crypto.randomUUID());
    return jsonResponse(chatResultFor(String(body.message ?? ""), threadId, crypto.randomUUID()));
  }
  return notImplemented(method, pathname);
}

function routeChatStream(
  method: string,
  pathname: string,
  init: RequestInit | undefined,
): Response {
  if (pathname !== "/api/chat/stream" || method !== "POST") return notImplemented(method, pathname);
  const body = requestBody(init);
  const threadId = String(body.thread_id ?? crypto.randomUUID());
  const traceId = crypto.randomUUID();
  const progress = buildProgressEvents(traceId);
  const payload = chatResultFor(String(body.message ?? ""), threadId, crypto.randomUUID());
  const terminal = buildTerminalEvent(progress.length + 1, traceId, payload);
  const frames = [...progress, terminal];

  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      for (const frame of frames) {
        await new Promise((resolve) => setTimeout(resolve, STREAM_FRAME_DELAY_MS));
        controller.enqueue(encoder.encode(sseFrame(frame)));
      }
      controller.close();
    },
  });
  return new Response(stream, { status: 200, headers: { "Content-Type": "text/event-stream" } });
}

function routeOwnerDataRuns(
  method: string,
  pathname: string,
  init: RequestInit | undefined,
): Response {
  if (pathname !== "/api/owner-data/runs/inspect" || method !== "POST")
    return notImplemented(method, pathname);
  const body = requestBody(init);
  const selector = String(body.run_id ?? body.trace_id ?? "demo-run");
  return jsonResponse(demoRunInspection(selector, selector));
}

function routeHealth(method: string, pathname: string): Response {
  if (pathname === "/api/health" && method === "GET") {
    return jsonResponse({ status: "ok" });
  }
  if (pathname === "/api/health/readiness" && method === "GET") {
    return jsonResponse(demoReadinessReport());
  }
  return notImplemented(method, pathname);
}

/** Replaces `globalThis.fetch` with an in-memory router covering the app's full critical
 *  path — catalog browse, chat (JSON + streamed), the typed pending-action confirmation
 *  flow, cart, checkout, orders and mock payments, plus the pre-existing shopping-tasks
 *  fixtures and the run inspector / readiness checks the status lights read. Anything not
 *  routed (owner-data memory management, admin AI health) returns a clearly-labeled 501
 *  rather than silently falling through to a real network call, so demo mode stays fully
 *  offline and honest about what it can't show yet.
 *  Idempotent: a second call is a no-op, and the returned function restores the original
 *  `fetch` and removes the on-screen badge. */
export function installDemoTransport(): () => void {
  if (installed) return () => {};
  installed = true;
  const originalFetch = globalThis.fetch;
  const taskStore = new DemoTaskStore();
  const commerce = new DemoCommerceStore();

  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = requestUrl(input);
    const method = requestMethod(input, init);
    const pathname = url.pathname;

    if (pathname === "/api/shopping-tasks" || pathname.startsWith("/api/shopping-tasks/")) {
      return routeShoppingTasks(taskStore, method, pathname, init);
    }
    if (pathname.startsWith("/api/catalog/")) return routeCatalog(method, pathname, url);
    if (pathname.startsWith("/api/pending-actions/") || pathname.startsWith("/api/pending-actions"))
      return routePendingActions(commerce, method, pathname, init);
    if (pathname === "/api/cart" || pathname.startsWith("/api/cart/"))
      return routeCart(commerce, method, pathname, init);
    if (pathname === "/api/checkout/preview" || pathname.startsWith("/api/orders"))
      return routeCheckoutAndOrders(commerce, method, pathname, init);
    if (pathname === "/api/chat/stream") return routeChatStream(method, pathname, init);
    if (pathname === "/api/chat") return routeChat(method, pathname, init);
    if (pathname === "/api/owner-data/runs/inspect")
      return routeOwnerDataRuns(method, pathname, init);
    if (pathname === "/api/health" || pathname === "/api/health/readiness")
      return routeHealth(method, pathname);
    return notImplemented(method, pathname);
  }) as typeof fetch;

  const removeBadge = injectDemoBadge();
  return () => {
    globalThis.fetch = originalFetch;
    removeBadge();
    installed = false;
  };
}
