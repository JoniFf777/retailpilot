import { describe, expect, it } from "vitest";
import { readApiError } from "./errors";

const orderErrorCodes = [
  "checkout_invalid", "checkout_expired", "checkout_unavailable", "cart_changed", "mixed_currency",
  "product_inactive", "sku_inactive", "inventory_missing", "insufficient_inventory", "price_changed",
  "idempotency_conflict", "order_not_found", "reservation_inconsistent", "idempotency_key_invalid", "cursor_invalid",
] as const;

describe("Phase 4A typed API errors", () => {
  it.each(orderErrorCodes)("recognizes %s as an Order error", async (code) => {
    const error = await readApiError(new Response(JSON.stringify({ code, message: code, details: {}, idempotent_replay: false }), { status: 409 }));
    expect(error.orderError?.code).toBe(code);
  });

  it("recognizes the Preview service-unavailable response separately", async () => {
    const error = await readApiError(new Response(JSON.stringify({ code: "checkout_unavailable", message: "unavailable", details: {} }), { status: 503 }));
    expect(error.checkoutError?.code).toBe("checkout_unavailable");
    expect(error.orderError?.code).toBe("checkout_unavailable");
  });

  it.each(["payment_declined", "payment_provider_unavailable", "payment_finalization_pending", "payment_in_progress", "idempotency_conflict"] as const)("recognizes %s as a Payment error", async (code) => {
    const error = await readApiError(new Response(JSON.stringify({ code, message: code, details: {}, idempotent_replay: false }), { status: 409 }));
    expect(error.paymentError?.code).toBe(code);
  });
});
