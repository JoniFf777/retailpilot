import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SessionProvider } from "../../app/session";
import { newCheckoutAttempt, readCheckoutAttempt, updateCheckoutAttempt } from "../checkout/checkoutAttempt";
import { checkoutPreviewQueryKey } from "../checkout/checkoutQuery";
import { ChatPage } from "./ChatPage";

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

describe("structured ShopMind Cart mutations", () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.restoreAllMocks();
  });

  it("clear an old CheckoutAttempt and Preview after structured add-to-cart confirm", async () => {
    const pending = { pending_action_id: "pa-checkout-clear", action_type: "add_to_cart", risk_class: "high", status: "pending", version: 1, expires_at: null, preview: "Add SKU", editable_fields: [{ field_type: "integer", field: "quantity", label: "Quantity", current_value: 1, min_value: 1, max_value: 20, required: true }], confirm_label: "Confirm", cancel_label: "Cancel" };
    const confirmed = { ...pending, status: "confirmed", version: 2 };
    const cart = { items: [], item_count: 0, total_quantity: 0, subtotal: null, currency: null, warnings: [] };
    const streamEvent = JSON.stringify({ sequence: 1, event_type: "run.result", timestamp: "2026-08-08T00:00:00Z", visibility: "client", payload: { answer: "Recommendation", status: "completed", tool_calls: [], run_id: "run-checkout-clear", recommendation_context: { source_run_id: "run-checkout-clear" }, recommendation: { schema_version: "shopmind.recommendation.v1", outcome: "recommended", ranking_policy_version: "v1", request_summary: "checkout clear", structured_constraints: {}, recommendations: [{ product_id: "product-1", sku_id: "sku-1", product_name: "Recommended product", sku_name: "Standard", money: { amount: "199.00", currency: "CNY" }, availability: { sale_status: "active", in_stock: true, available_quantity: 5 }, score: 90, reason: "fit", score_breakdown: [], specifications: [] }] } } });
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url.includes("/chat/stream")) return Promise.resolve(new Response(`event: run.result\nid: 1\ndata: ${streamEvent}\n\n`, { headers: { "Content-Type": "text/event-stream" } }));
      if (url.includes("/pending-actions/add-to-cart")) return Promise.resolve(jsonResponse(pending, 201));
      if (url.includes("/pending-actions/pa-checkout-clear/confirm")) return Promise.resolve(jsonResponse({ pending_action: confirmed, cart_item: null, idempotent_replay: false, requested_quantity: 1, cart_quantity: 1, price_changed: false }));
      if (url.includes("/cart")) return Promise.resolve(jsonResponse(cart));
      return Promise.resolve(jsonResponse({}));
    });
    vi.stubGlobal("fetch", fetchMock);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    updateCheckoutAttempt(newCheckoutAttempt("demo-user", "old-token"), "unknown");
    client.setQueryData(checkoutPreviewQueryKey("demo-user"), { checkout_token: "old-token" });
    render(<QueryClientProvider client={client}><SessionProvider><MemoryRouter><ChatPage /></MemoryRouter></SessionProvider></QueryClientProvider>);

    fireEvent.change(screen.getByTestId("chat-input"), { target: { value: "Find a recommended product" } });
    fireEvent.click(screen.getByTestId("send-button"));
    await screen.findByText("Recommended product");
    const selectButton = document.querySelector(".recommendation-card-actions .primary-button");
    expect(selectButton).not.toBeNull();
    fireEvent.click(selectButton as HTMLElement);
    await screen.findByTestId("action-confirm");
    fireEvent.change(screen.getByTestId("action-quantity"), { target: { value: "1" } });
    fireEvent.click(screen.getByTestId("action-confirm"));

    await waitFor(() => {
      expect(readCheckoutAttempt("demo-user")).toBeNull();
      expect(client.getQueryData(checkoutPreviewQueryKey("demo-user"))).toBeUndefined();
    });
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("/api/cart"))).toBe(true);
  });
});
