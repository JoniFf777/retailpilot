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
} from "./contracts";
import { readSseStream } from "./sse";

const API_BASE = "/api";

function idempotencyKey(): string {
  return crypto.randomUUID();
}

type RequestOptions = RequestInit & { idempotency?: "required" | "disabled"; idempotencyKey?: string };

function isPendingActionView(value: unknown): value is PendingActionView {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Record<string, unknown>;
  return typeof candidate.pending_action_id === "string"
    && (candidate.action_type === "add_to_cart" || candidate.action_type === "save_preference")
    && typeof candidate.risk_class === "string"
    && typeof candidate.status === "string"
    && typeof candidate.version === "number"
    && Array.isArray(candidate.editable_fields);
}

async function requestJson<T>(path: string, init: RequestOptions = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body) headers.set("Content-Type", "application/json");
  if (init.idempotencyKey) headers.set("Idempotency-Key", init.idempotencyKey);
  if (init.idempotency !== "disabled" && !headers.has("Idempotency-Key") && init.method && init.method !== "GET") {
    headers.set("Idempotency-Key", idempotencyKey());
  }

  const response = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (!response.ok) throw await readApiError(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const shopMindApi = {
  chat: (request: ChatRequest, signal?: AbortSignal) => requestJson<ChatResponse>("/chat", {
    method: "POST", body: JSON.stringify(request), signal,
  }),
  confirm: (request: ConfirmChatRequest, signal?: AbortSignal) => requestJson<ChatResponse>("/chat/confirm", {
    method: "POST", body: JSON.stringify(request), signal,
  }),
  inspectOwnerData: (userId: string, memoryLimit = 50, signal?: AbortSignal) => requestJson<OwnerDataSnapshot>("/owner-data/inspect", {
    method: "POST", body: JSON.stringify({ user_id: userId, memory_limit: memoryLimit }), signal,
  }),
  inspectRun: (request: { user_id: string; run_id?: string; trace_id?: string; event_limit?: number }, signal?: AbortSignal) => requestJson<OwnerRunInspection>("/owner-data/runs/inspect", {
    method: "POST", body: JSON.stringify(request), signal,
  }),
  correctMemory: (request: { user_id: string; memory_id: string; content: string }, signal?: AbortSignal) => requestJson<OwnerMemoryCorrection>("/owner-data/memory/correct", {
    method: "POST", body: JSON.stringify(request), signal,
  }),
  deleteMemory: (request: { user_id: string; memory_id: string }, signal?: AbortSignal) => requestJson<OwnerMemoryDeletion>("/owner-data/memory/delete", {
    method: "POST", body: JSON.stringify(request), signal,
  }),
  deleteOwnerData: (request: { user_id: string; deletion_request_id: string; confirmed: true }, signal?: AbortSignal) => requestJson<OwnerDataDeletion>("/owner-data/delete", {
    method: "POST", body: JSON.stringify(request), signal,
  }),
  health: (signal?: AbortSignal) => requestJson<HealthResponse>("/health", { signal }),
  readiness: async (signal?: AbortSignal) => {
    const response = await fetch(`${API_BASE}/health/readiness`, {
      headers: { Accept: "application/json" }, signal,
    });
    if (response.ok || response.status === 503) return (await response.json()) as ReadinessResponse;
    throw await readApiError(response);
  },
  streamChat: async function* (request: ChatRequest, signal?: AbortSignal) {
    const response = await fetch(`${API_BASE}/chat/stream`, {
      method: "POST",
      headers: { Accept: "text/event-stream", "Content-Type": "application/json", "Idempotency-Key": idempotencyKey() },
      body: JSON.stringify(request),
      signal,
    });
    if (!response.ok) throw await readApiError(response);
    if (!response.body) throw new ApiError("ShopMind stream returned no body.", response.status, null, null);
    yield* readSseStream(response.body);
  },
  createAddToCartPendingAction: (request: AddToCartPendingActionRequest, signal?: AbortSignal) => requestJson<PendingActionView>("/pending-actions/add-to-cart", {
    method: "POST", body: JSON.stringify(request), signal, idempotency: "disabled",
  }),
  getPendingAction: (pendingActionId: string, threadId: string, userId?: string, signal?: AbortSignal) => {
    const query = new URLSearchParams({ thread_id: threadId });
    if (userId) query.set("user_id", userId);
    return requestJson<unknown>(`/pending-actions/${encodeURIComponent(pendingActionId)}?${query.toString()}`, { signal, idempotency: "disabled" }).then((value) => {
      if (!isPendingActionView(value)) throw new ApiError("Pending action response was invalid.", 200, null, null);
      return value;
    });
  },
  confirmPendingAction: (pendingActionId: string, request: PendingActionTransitionRequest, signal?: AbortSignal) => requestJson<PendingActionTransitionResponse>(`/pending-actions/${encodeURIComponent(pendingActionId)}/confirm`, {
    method: "POST", body: JSON.stringify(request), signal, idempotency: "disabled",
  }),
  cancelPendingAction: (pendingActionId: string, request: PendingActionCancelRequest, signal?: AbortSignal) => requestJson<PendingActionTransitionResponse>(`/pending-actions/${encodeURIComponent(pendingActionId)}/cancel`, {
    method: "POST", body: JSON.stringify(request), signal, idempotency: "disabled",
  }),
  getCart: (userId?: string, signal?: AbortSignal) => {
    const query = userId ? `?user_id=${encodeURIComponent(userId)}` : "";
    return requestJson<CartResponse>(`/cart${query}`, { signal, idempotency: "disabled" });
  },
  updateCartItem: (cartItemId: string, request: UpdateCartItemRequest, signal?: AbortSignal) => requestJson<CartMutationResponse>(`/cart/items/${encodeURIComponent(cartItemId)}`, {
    method: "PATCH", body: JSON.stringify(request), signal, idempotency: "disabled",
  }),
  deleteCartItem: (cartItemId: string, signal?: AbortSignal) => requestJson<void>(`/cart/items/${encodeURIComponent(cartItemId)}`, {
    method: "DELETE", signal, idempotency: "disabled",
  }),
  clearCart: (signal?: AbortSignal) => requestJson<void>("/cart", {
    method: "DELETE", signal, idempotency: "disabled",
  }),
  checkoutPreview: (userId?: string, signal?: AbortSignal) => {
    const query = userId ? `?user_id=${encodeURIComponent(userId)}` : "";
    return requestJson<CheckoutPreview>(`/checkout/preview${query}`, {
      method: "POST", body: JSON.stringify({}), signal,
    });
  },
  createOrder: (request: CreateOrderRequest, idempotencyKey: string, userId?: string, signal?: AbortSignal) => {
    const query = userId ? `?user_id=${encodeURIComponent(userId)}` : "";
    return requestJson<CreateOrderResponse>(`/orders${query}`, {
      method: "POST", body: JSON.stringify(request), signal, idempotencyKey,
    });
  },
  listOrders: (userId?: string, limit = 20, cursor?: string | null, signal?: AbortSignal) => {
    const query = new URLSearchParams({ limit: String(limit) });
    if (userId) query.set("user_id", userId);
    if (cursor) query.set("cursor", cursor);
    return requestJson<OrderListResponse>(`/orders?${query.toString()}`, { signal, idempotency: "disabled" });
  },
  getOrder: (orderId: string, userId?: string, signal?: AbortSignal) => {
    const query = userId ? `?user_id=${encodeURIComponent(userId)}` : "";
    return requestJson<OrderView>(`/orders/${encodeURIComponent(orderId)}${query}`, { signal, idempotency: "disabled" });
  },
  cancelOrder: (orderId: string, userId?: string, signal?: AbortSignal) => {
    const query = userId ? `?user_id=${encodeURIComponent(userId)}` : "";
    return requestJson<CancelOrderResponse>(`/orders/${encodeURIComponent(orderId)}/cancel${query}`, {
      method: "POST", signal, idempotency: "disabled",
    });
  },
  createPayment: (orderId: string, request: PaymentAttemptRequest, idempotencyKey: string, userId?: string, signal?: AbortSignal) => {
    const query = userId ? `?user_id=${encodeURIComponent(userId)}` : "";
    return requestJson<PaymentAttemptResponse>(`/orders/${encodeURIComponent(orderId)}/payments${query}`, {
      method: "POST", body: JSON.stringify(request), signal, idempotencyKey,
    });
  },
  listPayments: (orderId: string, userId?: string, signal?: AbortSignal) => {
    const query = userId ? `?user_id=${encodeURIComponent(userId)}` : "";
    return requestJson<PaymentAttemptListResponse>(`/orders/${encodeURIComponent(orderId)}/payments${query}`, {
      signal, idempotency: "disabled",
    });
  },
};
