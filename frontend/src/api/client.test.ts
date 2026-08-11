import { beforeEach, describe, expect, it, vi } from "vitest";
import { shopMindApi } from "./client";
import { readApiError } from "./errors";

describe("dedicated pending-action client", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("sends the exact SKU create payload without an idempotency key", async () => {
    const pending = { pending_action_id: "pa-1", action_type: "add_to_cart", risk_class: "high", status: "pending", version: 1, expires_at: null, preview: {}, editable_fields: [] };
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(pending), { status: 201, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
    await shopMindApi.createAddToCartPendingAction({ thread_id: "thread-1", source_run_id: "run-1", sku_id: "sku-1", quantity: 1 });
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/pending-actions/add-to-cart");
    expect(JSON.parse(String(init.body))).toEqual({ thread_id: "thread-1", source_run_id: "run-1", sku_id: "sku-1", quantity: 1 });
    expect(new Headers(init.headers).has("Idempotency-Key")).toBe(false);
  });

  it("uses dedicated confirm/cancel endpoints without idempotency keys", async () => {
    const response = { pending_action: { pending_action_id: "pa-1", action_type: "add_to_cart", risk_class: "high", status: "confirmed", version: 2, expires_at: null, preview: {}, editable_fields: [] }, idempotent_replay: false };
    const fetchMock = vi.fn().mockImplementation(() => new Response(JSON.stringify(response), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
    await shopMindApi.confirmPendingAction("pa-1", { thread_id: "thread-1", expected_version: 1, updated_fields: { quantity: 2 } });
    await shopMindApi.cancelPendingAction("pa-1", { thread_id: "thread-1", expected_version: 1 });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    for (const call of fetchMock.mock.calls) expect(new Headers((call[1] as RequestInit).headers).has("Idempotency-Key")).toBe(false);
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain("/pending-actions/pa-1/confirm");
    expect(String(fetchMock.mock.calls[1]?.[0])).toContain("/pending-actions/pa-1/cancel");
  });

  it("sends the exact Cart PATCH body and parses Cart errors separately", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ item: {}, cart: {} }), { status: 200, headers: { "Content-Type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ code: "cart_version_conflict", message: "version conflict", details: { current_version: 2 } }), { status: 409, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);

    await shopMindApi.updateCartItem("cart-1", { expected_version: 1, quantity: 3 });
    const request = JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body)) as Record<string, unknown>;
    expect(request).toEqual({ expected_version: 1, quantity: 3 });
    expect(Object.keys(request)).not.toEqual(expect.arrayContaining(["sku_id", "product_id", "price", "currency", "inventory", "user_id"]));

    await expect(shopMindApi.updateCartItem("cart-1", { expected_version: 1, quantity: 3 })).rejects.toMatchObject({
      cartError: { code: "cart_version_conflict", details: { current_version: 2 } },
    });
  });

  it("treats item and Cart DELETE 204 responses as successful without parsing JSON", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);

    await shopMindApi.deleteCartItem("cart-1");
    await shopMindApi.clearCart();

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/cart/items/cart-1");
    expect(fetchMock.mock.calls[1]?.[0]).toBe("/api/cart");
    expect(new Headers(fetchMock.mock.calls[0]?.[1]?.headers).has("Idempotency-Key")).toBe(false);
  });

  it("does not treat arbitrary JSON as a CartErrorResponse", async () => {
    const error = await readApiError(new Response(JSON.stringify({ code: "not-a-cart-code", message: "bad" }), { status: 400 }));
    expect(error.cartError).toBeNull();
  });

  it("uses the generated Phase 4A endpoints and preserves an explicit order key", async () => {
    const preview = { checkout_token: "checkout-1", can_create_order: true, items: [], item_count: 0, total_quantity: 0, subtotal: null, currency: "CNY", warnings: [] };
    const order = { order: { order_id: "order-1", user_id: "user-a", status: "pending_payment", currency: "CNY", subtotal: { amount: "0.00", currency: "CNY" }, total: { amount: "0.00", currency: "CNY" }, items: [], version: 1, created_at: "2026-08-08T00:00:00Z", updated_at: "2026-08-08T00:00:00Z" }, idempotent_replay: false };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(preview), { status: 200, headers: { "Content-Type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify(order), { status: 201, headers: { "Content-Type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [order.order], next_cursor: null }), { status: 200, headers: { "Content-Type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify(order.order), { status: 200, headers: { "Content-Type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ order: { ...order.order, status: "cancelled" }, idempotent_replay: false }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);

    await shopMindApi.checkoutPreview("user-a");
    await shopMindApi.createOrder({ checkout_token: "checkout-1" }, "request-1", "user-a");
    await shopMindApi.listOrders("user-a");
    await shopMindApi.getOrder("order-1", "user-a");
    await shopMindApi.cancelOrder("order-1", "user-a");

    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "/api/checkout/preview?user_id=user-a",
      "/api/orders?user_id=user-a",
      "/api/orders?limit=20&user_id=user-a",
      "/api/orders/order-1?user_id=user-a",
      "/api/orders/order-1/cancel?user_id=user-a",
    ]);
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual({});
    expect(JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body))).toEqual({ checkout_token: "checkout-1" });
    expect(new Headers(fetchMock.mock.calls[1]?.[1]?.headers).get("Idempotency-Key")).toBe("request-1");
    expect(fetchMock.mock.calls[4]?.[1]?.body).toBeUndefined();
    expect(new Headers(fetchMock.mock.calls[4]?.[1]?.headers).has("Idempotency-Key")).toBe(false);
  });

  it("parses typed Checkout and Order errors", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ code: "checkout_unavailable", message: "preview unavailable", details: {} }), { status: 503 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ code: "checkout_unavailable", message: "temporarily unavailable", details: {} }), { status: 503 }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(shopMindApi.checkoutPreview()).rejects.toMatchObject({ checkoutError: { code: "checkout_unavailable" }, status: 503 });
    await expect(shopMindApi.createOrder({ checkout_token: "checkout-1" }, "request-1")).rejects.toMatchObject({ orderError: { code: "checkout_unavailable" }, status: 503 });
  });

  it("sends the exact Mock Payment body and keeps Idempotency-Key off history reads", async () => {
    const order = { order_id: "order-1", status: "pending_payment", currency: "CNY", subtotal: { amount: "5999.00", currency: "CNY" }, total: { amount: "5999.00", currency: "CNY" }, items: [], version: 1, created_at: "2026-08-08T00:00:00Z", updated_at: "2026-08-08T00:00:00Z" };
    const attempt = { attempt_id: "attempt-1", order_id: "order-1", provider: "mock", status: "unknown", amount: { amount: "5999.00", currency: "CNY" }, failure_code: "provider_timeout", provider_result_at: "2026-08-08T00:00:00Z", created_at: "2026-08-08T00:00:00Z", updated_at: "2026-08-08T00:00:00Z", completed_at: null };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ payment_attempt: attempt, order, idempotent_replay: false }), { status: 202, headers: { "Content-Type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [attempt] }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);

    await shopMindApi.createPayment("order-1", { provider: "mock", payment_method_ref: "mock-web" }, "payment-key", "user-a");
    await shopMindApi.listPayments("order-1", "user-a");

    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/orders/order-1/payments?user_id=user-a");
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual({ provider: "mock", payment_method_ref: "mock-web" });
    expect(new Headers(fetchMock.mock.calls[0]?.[1]?.headers).get("Idempotency-Key")).toBe("payment-key");
    expect(fetchMock.mock.calls[1]?.[0]).toBe("/api/orders/order-1/payments?user_id=user-a");
    expect(fetchMock.mock.calls[1]?.[1]?.body).toBeUndefined();
    expect(new Headers(fetchMock.mock.calls[1]?.[1]?.headers).has("Idempotency-Key")).toBe(false);
  });
});
