import { ApiError, readApiError } from "./errors";
import type {
  ChatRequest,
  ChatResponse,
  ConfirmChatRequest,
  CancelOrderResponse,
  CheckoutPreview,
  CreateOrderRequest,
  CreateOrderResponse,
  AddToCartPendingActionRequest,
  CartMutationResponse,
  CartResponse,
  PendingActionCancelRequest,
  PendingActionTransitionRequest,
  PendingActionTransitionResponse,
  PendingActionView,
  HealthResponse,
  OwnerDataDeletion,
  OwnerDataSnapshot,
  OwnerMemoryCorrection,
  OwnerMemoryDeletion,
  OwnerRunInspection,
  OrderListResponse,
  OrderView,
  PaymentAttemptListResponse,
  PaymentAttemptRequest,
  PaymentAttemptResponse,
  ReadinessResponse,
  UpdateCartItemRequest,
  CatalogCategoryListResponse,
  CatalogProductListResponse,
  CatalogProductDetail,
  CatalogBrowseAddToCartPendingActionRequest,
} from "./contracts";
import { parseSseText, readSseStream } from "./sse";
import type {
  ShoppingTaskListItem,
  ShoppingTaskSnapshot,
  TaskKind,
} from "../features/tasks/taskTypes";

const API_BASE = "/api";

function idempotencyKey(): string {
  return crypto.randomUUID();
}

type RequestOptions = RequestInit & {
  idempotency?: "required" | "disabled";
  idempotencyKey?: string;
};

export type ShoppingTaskEvent = {
  sequence: number;
  type: string;
  payload: Record<string, unknown>;
};

function isPendingActionView(value: unknown): value is PendingActionView {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.pending_action_id === "string" &&
    (candidate.action_type === "add_to_cart" || candidate.action_type === "save_preference") &&
    typeof candidate.risk_class === "string" &&
    typeof candidate.status === "string" &&
    typeof candidate.version === "number" &&
    Array.isArray(candidate.editable_fields)
  );
}

async function requestJson<T>(path: string, init: RequestOptions = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body) headers.set("Content-Type", "application/json");
  if (init.idempotencyKey) headers.set("Idempotency-Key", init.idempotencyKey);
  if (
    init.idempotency !== "disabled" &&
    !headers.has("Idempotency-Key") &&
    init.method &&
    init.method !== "GET"
  ) {
    headers.set("Idempotency-Key", idempotencyKey());
  }

  const response = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (!response.ok) throw await readApiError(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const shopMindApi = {
  listCatalogCategories: (signal?: AbortSignal) =>
    requestJson<CatalogCategoryListResponse>("/catalog/categories", {
      signal,
      idempotency: "disabled",
    }),
  listCatalogProducts: (category: string, limit = 24, offset = 0, signal?: AbortSignal) => {
    const query = new URLSearchParams({ category, limit: String(limit), offset: String(offset) });
    return requestJson<CatalogProductListResponse>(`/catalog/products?${query.toString()}`, {
      signal,
      idempotency: "disabled",
    });
  },
  getCatalogProduct: (productCode: string, signal?: AbortSignal) =>
    requestJson<CatalogProductDetail>(`/catalog/products/${encodeURIComponent(productCode)}`, {
      signal,
      idempotency: "disabled",
    }),
  listShoppingTasks: (userId: string, signal?: AbortSignal) =>
    requestJson<{ items: ShoppingTaskListItem[]; limit: number; offset: number }>(
      `/shopping-tasks?user_id=${encodeURIComponent(userId)}`,
      { signal, idempotency: "disabled" },
    ),
  getShoppingTask: (taskId: string, userId: string, signal?: AbortSignal) =>
    requestJson<ShoppingTaskSnapshot>(
      `/shopping-tasks/${encodeURIComponent(taskId)}?user_id=${encodeURIComponent(userId)}`,
      { signal, idempotency: "disabled" },
    ),
  streamShoppingTaskEvents: async (
    taskId: string,
    userId: string,
    afterSequence: number,
    signal?: AbortSignal,
  ): Promise<ShoppingTaskEvent[]> => {
    const query = new URLSearchParams({ user_id: userId, after_sequence: String(afterSequence) });
    const response = await fetch(
      `${API_BASE}/shopping-tasks/${encodeURIComponent(taskId)}/events?${query.toString()}`,
      { headers: { Accept: "text/event-stream" }, signal },
    );
    if (!response.ok) throw await readApiError(response);
    const text = await response.text();
    return parseSseText(text).flatMap((frame) => {
      try {
        const value: unknown = JSON.parse(frame.data);
        if (!value || typeof value !== "object") return [];
        const payload = value as Record<string, unknown>;
        const sequence = Number(frame.id);
        const type = typeof payload.type === "string" ? payload.type : frame.event;
        if (!Number.isInteger(sequence) || sequence < 1 || !type) return [];
        return [{ sequence, type, payload }];
      } catch {
        return [];
      }
    });
  },
  createShoppingTask: (
    request: {
      user_id: string;
      kind: TaskKind;
      goal_text: string;
      known_facts?: unknown[];
      thread_id?: string;
    },
    idempotencyKey?: string,
    signal?: AbortSignal,
  ) =>
    requestJson<{ task_id: string; status: string; version: number; mode: string }>(
      "/shopping-tasks",
      { method: "POST", body: JSON.stringify(request), idempotencyKey, signal },
    ),
  cancelShoppingTask: (
    taskId: string,
    request: { user_id: string; expected_version: number },
    idempotencyKey?: string,
    signal?: AbortSignal,
  ) =>
    requestJson<{ task_id: string; status: string; version: number }>(
      `/shopping-tasks/${encodeURIComponent(taskId)}/cancel`,
      { method: "POST", body: JSON.stringify(request), idempotencyKey, signal },
    ),
  addShoppingTaskInputs: (
    taskId: string,
    request: {
      user_id: string;
      expected_version: number;
      facts?: unknown[];
      feedback?: Record<string, unknown>;
    },
    idempotencyKey?: string,
    signal?: AbortSignal,
  ) =>
    requestJson<{ task_id: string; status: string; version: number }>(
      `/shopping-tasks/${encodeURIComponent(taskId)}/inputs`,
      { method: "POST", body: JSON.stringify(request), idempotencyKey, signal },
    ),
  prepareShoppingTaskAction: (
    taskId: string,
    request: {
      user_id: string;
      expected_version: number;
      action_type: "add_bundle_to_cart" | "save_after_sales_draft";
    },
    idempotencyKey?: string,
    signal?: AbortSignal,
  ) =>
    requestJson<{
      action_id: string;
      action_type: string;
      status: string;
      version: number;
      expires_at: string;
      payload: Record<string, unknown>;
    }>(`/shopping-tasks/${encodeURIComponent(taskId)}/actions`, {
      method: "POST",
      body: JSON.stringify(request),
      idempotencyKey,
      signal,
    }),
  confirmShoppingTaskAction: (
    taskId: string,
    actionId: string,
    request: { user_id: string; expected_version: number; confirmed: boolean },
    idempotencyKey?: string,
    signal?: AbortSignal,
  ) =>
    requestJson<Record<string, unknown>>(
      `/shopping-tasks/${encodeURIComponent(taskId)}/actions/${encodeURIComponent(actionId)}/confirm`,
      { method: "POST", body: JSON.stringify(request), idempotencyKey, signal },
    ),
  chat: (request: ChatRequest, idempotencyKey?: string, signal?: AbortSignal) =>
    requestJson<ChatResponse>("/chat", {
      method: "POST",
      body: JSON.stringify(request),
      signal,
      idempotencyKey,
    }),
  confirm: (request: ConfirmChatRequest, signal?: AbortSignal) =>
    requestJson<ChatResponse>("/chat/confirm", {
      method: "POST",
      body: JSON.stringify(request),
      signal,
    }),
  inspectOwnerData: (userId: string, memoryLimit = 50, signal?: AbortSignal) =>
    requestJson<OwnerDataSnapshot>("/owner-data/inspect", {
      method: "POST",
      body: JSON.stringify({ user_id: userId, memory_limit: memoryLimit }),
      signal,
    }),
  inspectRun: (
    request: { user_id: string; run_id?: string; trace_id?: string; event_limit?: number },
    signal?: AbortSignal,
  ) =>
    requestJson<OwnerRunInspection>("/owner-data/runs/inspect", {
      method: "POST",
      body: JSON.stringify(request),
      signal,
    }),
  correctMemory: (
    request: { user_id: string; memory_id: string; content: string },
    signal?: AbortSignal,
  ) =>
    requestJson<OwnerMemoryCorrection>("/owner-data/memory/correct", {
      method: "POST",
      body: JSON.stringify(request),
      signal,
    }),
  deleteMemory: (request: { user_id: string; memory_id: string }, signal?: AbortSignal) =>
    requestJson<OwnerMemoryDeletion>("/owner-data/memory/delete", {
      method: "POST",
      body: JSON.stringify(request),
      signal,
    }),
  deleteOwnerData: (
    request: { user_id: string; deletion_request_id: string; confirmed: true },
    signal?: AbortSignal,
  ) =>
    requestJson<OwnerDataDeletion>("/owner-data/delete", {
      method: "POST",
      body: JSON.stringify(request),
      signal,
    }),
  health: (signal?: AbortSignal) => requestJson<HealthResponse>("/health", { signal }),
  readiness: async (signal?: AbortSignal) => {
    const response = await fetch(`${API_BASE}/health/readiness`, {
      headers: { Accept: "application/json" },
      signal,
    });
    if (response.ok || response.status === 503) return (await response.json()) as ReadinessResponse;
    throw await readApiError(response);
  },
  streamChat: async function* (
    request: ChatRequest,
    idempotencyKey?: string,
    signal?: AbortSignal,
  ) {
    const headers = new Headers({
      Accept: "text/event-stream",
      "Content-Type": "application/json",
    });
    if (idempotencyKey) headers.set("Idempotency-Key", idempotencyKey);
    const response = await fetch(`${API_BASE}/chat/stream`, {
      method: "POST",
      headers,
      body: JSON.stringify(request),
      signal,
    });
    if (!response.ok) throw await readApiError(response);
    if (!response.body)
      throw new ApiError("ShopMind stream returned no body.", response.status, null, null);
    yield* readSseStream(response.body);
  },
  createAddToCartPendingAction: (request: AddToCartPendingActionRequest, signal?: AbortSignal) =>
    requestJson<PendingActionView>("/pending-actions/add-to-cart", {
      method: "POST",
      body: JSON.stringify(request),
      signal,
      idempotency: "disabled",
    }),
  createCatalogBrowsePendingAction: (
    request: CatalogBrowseAddToCartPendingActionRequest,
    signal?: AbortSignal,
  ) =>
    requestJson<PendingActionView>("/pending-actions/catalog-add-to-cart", {
      method: "POST",
      body: JSON.stringify(request),
      signal,
      idempotency: "disabled",
    }),
  getPendingAction: (
    pendingActionId: string,
    threadId: string,
    userId?: string,
    signal?: AbortSignal,
  ) => {
    const query = new URLSearchParams({ thread_id: threadId });
    if (userId) query.set("user_id", userId);
    return requestJson<unknown>(
      `/pending-actions/${encodeURIComponent(pendingActionId)}?${query.toString()}`,
      { signal, idempotency: "disabled" },
    ).then((value) => {
      if (!isPendingActionView(value))
        throw new ApiError("Pending action response was invalid.", 200, null, null);
      return value;
    });
  },
  confirmPendingAction: (
    pendingActionId: string,
    request: PendingActionTransitionRequest,
    signal?: AbortSignal,
  ) =>
    requestJson<PendingActionTransitionResponse>(
      `/pending-actions/${encodeURIComponent(pendingActionId)}/confirm`,
      {
        method: "POST",
        body: JSON.stringify(request),
        signal,
        idempotency: "disabled",
      },
    ),
  cancelPendingAction: (
    pendingActionId: string,
    request: PendingActionCancelRequest,
    signal?: AbortSignal,
  ) =>
    requestJson<PendingActionTransitionResponse>(
      `/pending-actions/${encodeURIComponent(pendingActionId)}/cancel`,
      {
        method: "POST",
        body: JSON.stringify(request),
        signal,
        idempotency: "disabled",
      },
    ),
  getCart: (userId?: string, signal?: AbortSignal) => {
    const query = userId ? `?user_id=${encodeURIComponent(userId)}` : "";
    return requestJson<CartResponse>(`/cart${query}`, { signal, idempotency: "disabled" });
  },
  updateCartItem: (cartItemId: string, request: UpdateCartItemRequest, signal?: AbortSignal) =>
    requestJson<CartMutationResponse>(`/cart/items/${encodeURIComponent(cartItemId)}`, {
      method: "PATCH",
      body: JSON.stringify(request),
      signal,
      idempotency: "disabled",
    }),
  deleteCartItem: (cartItemId: string, signal?: AbortSignal) =>
    requestJson<void>(`/cart/items/${encodeURIComponent(cartItemId)}`, {
      method: "DELETE",
      signal,
      idempotency: "disabled",
    }),
  clearCart: (signal?: AbortSignal) =>
    requestJson<void>("/cart", {
      method: "DELETE",
      signal,
      idempotency: "disabled",
    }),
  checkoutPreview: (userId?: string, signal?: AbortSignal) => {
    const query = userId ? `?user_id=${encodeURIComponent(userId)}` : "";
    return requestJson<CheckoutPreview>(`/checkout/preview${query}`, {
      method: "POST",
      body: JSON.stringify({}),
      signal,
    });
  },
  createOrder: (
    request: CreateOrderRequest,
    idempotencyKey: string,
    userId?: string,
    signal?: AbortSignal,
  ) => {
    const query = userId ? `?user_id=${encodeURIComponent(userId)}` : "";
    return requestJson<CreateOrderResponse>(`/orders${query}`, {
      method: "POST",
      body: JSON.stringify(request),
      signal,
      idempotencyKey,
    });
  },
  listOrders: (userId?: string, limit = 20, cursor?: string | null, signal?: AbortSignal) => {
    const query = new URLSearchParams({ limit: String(limit) });
    if (userId) query.set("user_id", userId);
    if (cursor) query.set("cursor", cursor);
    return requestJson<OrderListResponse>(`/orders?${query.toString()}`, {
      signal,
      idempotency: "disabled",
    });
  },
  getOrder: (orderId: string, userId?: string, signal?: AbortSignal) => {
    const query = userId ? `?user_id=${encodeURIComponent(userId)}` : "";
    return requestJson<OrderView>(`/orders/${encodeURIComponent(orderId)}${query}`, {
      signal,
      idempotency: "disabled",
    });
  },
  cancelOrder: (orderId: string, userId?: string, signal?: AbortSignal) => {
    const query = userId ? `?user_id=${encodeURIComponent(userId)}` : "";
    return requestJson<CancelOrderResponse>(
      `/orders/${encodeURIComponent(orderId)}/cancel${query}`,
      {
        method: "POST",
        signal,
        idempotency: "disabled",
      },
    );
  },
  createPayment: (
    orderId: string,
    request: PaymentAttemptRequest,
    idempotencyKey: string,
    userId?: string,
    signal?: AbortSignal,
  ) => {
    const query = userId ? `?user_id=${encodeURIComponent(userId)}` : "";
    return requestJson<PaymentAttemptResponse>(
      `/orders/${encodeURIComponent(orderId)}/payments${query}`,
      {
        method: "POST",
        body: JSON.stringify(request),
        signal,
        idempotencyKey,
      },
    );
  },
  listPayments: (orderId: string, userId?: string, signal?: AbortSignal) => {
    const query = userId ? `?user_id=${encodeURIComponent(userId)}` : "";
    return requestJson<PaymentAttemptListResponse>(
      `/orders/${encodeURIComponent(orderId)}/payments${query}`,
      {
        signal,
        idempotency: "disabled",
      },
    );
  },
};
