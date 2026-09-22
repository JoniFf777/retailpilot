import type { TaskKind } from "../api/contracts";
import { DemoHttpError, DemoTaskStore } from "./store";

const API_PREFIX = "/api/shopping-tasks";
const BADGE_ID = "retailpilot-demo-badge";

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
      return jsonResponse(store.get(taskId));
    }
    if (segments.length === 2 && action === "events" && method === "GET") {
      store.get(taskId);
      return emptyEventStream();
    }
    if (segments.length === 2 && action === "cancel" && method === "POST") {
      const body = requestBody(init);
      return jsonResponse(store.cancel(taskId, Number(body.expected_version)));
    }
    if (segments.length === 2 && action === "inputs" && method === "POST") {
      const body = requestBody(init);
      return jsonResponse(store.addInputs(taskId, Number(body.expected_version)));
    }
    if (segments.length === 2 && action === "actions" && method === "POST") {
      const body = requestBody(init);
      return jsonResponse(
        store.prepareAction(
          taskId,
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
          taskId,
          actionId,
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

/** Replaces `globalThis.fetch` with an in-memory router over the shopping-tasks fixtures
 *  (the only endpoints P1.5 needs faked — see docs/frontend_redesign_v2_plan_3.md §3/§4).
 *  Everything else returns a clearly-labeled 501 rather than silently falling through to a
 *  real network call, so demo mode stays fully offline and honest about what it can't show yet.
 *  Idempotent: a second call is a no-op, and the returned function restores the original
 *  `fetch` and removes the on-screen badge. */
export function installDemoTransport(): () => void {
  if (installed) return () => {};
  installed = true;
  const originalFetch = globalThis.fetch;
  const store = new DemoTaskStore();

  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = requestUrl(input);
    const method = requestMethod(input, init);
    if (url.pathname !== API_PREFIX && !url.pathname.startsWith(`${API_PREFIX}/`)) {
      return notImplemented(method, url.pathname);
    }
    return routeShoppingTasks(store, method, url.pathname, init);
  }) as typeof fetch;

  const removeBadge = injectDemoBadge();
  return () => {
    globalThis.fetch = originalFetch;
    removeBadge();
    installed = false;
  };
}
