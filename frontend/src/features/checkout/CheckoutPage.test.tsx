import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SessionProvider } from "../../app/session";
import { useSession } from "../../app/useSession";
import { newCheckoutAttempt, readCheckoutAttempt, updateCheckoutAttempt } from "./checkoutAttempt";
import { CheckoutPage } from "./CheckoutPage";
import { OrderDetailPage } from "../orders/OrderDetailPage";

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function preview(overrides: Record<string, unknown> = {}) {
  return {
    items: [{ cart_item_id: "cart-1", sku_id: "sku-1", product_name: "Notebook", sku_name: "16G / 512G", quantity: 2, unit_money: { amount: "5999.00", currency: "CNY" }, subtotal_money: { amount: "11998.00", currency: "CNY" }, availability: { sale_status: "active", available_quantity: 8, in_stock: true }, version: 1 }],
    item_count: 1,
    total_quantity: 2,
    subtotal: { amount: "11998.00", currency: "CNY" },
    currency: "CNY",
    warnings: [],
    can_create_order: true,
    checkout_token: "checkout-token-1",
    expires_at: "2026-08-08T00:10:00Z",
    revalidation_required: true,
    ...overrides,
  };
}

function orderResponse() {
  return {
    order: { order_id: "order-1", status: "pending_payment", currency: "CNY", subtotal: { amount: "11998.00", currency: "CNY" }, total: { amount: "11998.00", currency: "CNY" }, items: [{ item_id: "order-item-1", sku_id: "sku-1", product_code: "NOTEBOOK", product_name: "Notebook", sku_code: "SKU-1", sku_name: "16G / 512G", unit_money: { amount: "5999.00", currency: "CNY" }, quantity: 2, subtotal_money: { amount: "11998.00", currency: "CNY" } }], version: 1, created_at: "2026-08-08T00:00:00Z", updated_at: "2026-08-08T00:00:00Z" },
    idempotent_replay: false,
  };
}

function renderCheckout(fetchMock: ReturnType<typeof vi.fn>) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  vi.stubGlobal("fetch", fetchMock);
  return render(<QueryClientProvider client={queryClient}><SessionProvider><MemoryRouter initialEntries={["/checkout"]}><Routes><Route element={<CheckoutPage />} path="/checkout" /><Route element={<OrderDetailPage />} path="/orders/:orderId" /></Routes></MemoryRouter></SessionProvider></QueryClientProvider>);
}

function IdentitySwitch() {
  const { setUserId } = useSession();
  return <button onClick={() => setUserId("user-b")} type="button">Switch identity</button>;
}

function renderCheckoutWithIdentitySwitch(fetchMock: ReturnType<typeof vi.fn>) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  vi.stubGlobal("fetch", fetchMock);
  render(<QueryClientProvider client={queryClient}><SessionProvider><IdentitySwitch /><MemoryRouter initialEntries={["/checkout"]}><Routes><Route element={<CheckoutPage />} path="/checkout" /><Route element={<OrderDetailPage />} path="/orders/:orderId" /></Routes></MemoryRouter></SessionProvider></QueryClientProvider>);
}

describe("Checkout Preview and explicit Order creation", () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.restoreAllMocks();
  });

  it("renders the server snapshot and never creates an order while Preview is blocked", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(preview({ can_create_order: false, checkout_token: null, warnings: [{ code: "insufficient_inventory", cart_item_id: "cart-1", sku_id: "sku-1", message: "Only 1 available" }] })));
    renderCheckout(fetchMock);
    expect(await screen.findByTestId("checkout-preview")).toHaveTextContent("Notebook");
    expect(screen.getByTestId("checkout-preview")).toHaveTextContent("Only 1 available");
    expect(screen.getByTestId("checkout-preview")).toHaveTextContent("CNY 11998.00");
    expect(screen.queryByRole("button", { name: "Confirm order" })).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("creates exactly one Order for a double-click and sends the preview token and key", async () => {
    let resolveOrder: ((value: Response) => void) | undefined;
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(preview()))
      .mockImplementationOnce(() => new Promise<Response>((resolve) => { resolveOrder = resolve; }));
    renderCheckout(fetchMock);
    await screen.findByRole("button", { name: "Confirm order" });
    const confirmButton = screen.getByRole("button", { name: "Confirm order" });
    fireEvent.click(confirmButton);
    fireEvent.click(confirmButton);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(screen.queryByTestId("checkout-recovery")).not.toBeInTheDocument();
    const firstOrderRequest = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(JSON.parse(String(firstOrderRequest[1].body))).toEqual({ checkout_token: "checkout-token-1" });
    expect(new Headers(firstOrderRequest[1].headers).get("Idempotency-Key")).toMatch(/^request-/);
    resolveOrder?.(jsonResponse(orderResponse(), 201));
    expect(await screen.findByTestId("order-confirmation")).toBeInTheDocument();
  });

  it("retries a response-lost submission with the same key and token", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(preview()))
      .mockRejectedValueOnce(new TypeError("response lost"))
      .mockResolvedValueOnce(jsonResponse(orderResponse(), 201));
    renderCheckout(fetchMock);
    await screen.findByRole("button", { name: "Confirm order" });
    fireEvent.click(screen.getByRole("button", { name: "Confirm order" }));
    await screen.findByTestId("checkout-recovery");
    const firstRequest = fetchMock.mock.calls[1] as [string, RequestInit];
    const firstKey = new Headers(firstRequest[1].headers).get("Idempotency-Key");
    fireEvent.click(screen.getByRole("button", { name: "Retry submission" }));
    await screen.findByTestId("order-confirmation");
    const retryRequest = fetchMock.mock.calls[2] as [string, RequestInit];
    expect(new Headers(retryRequest[1].headers).get("Idempotency-Key")).toBe(firstKey);
    expect(JSON.parse(String(retryRequest[1].body))).toEqual({ checkout_token: "checkout-token-1" });
  });

  it.each(["price_changed", "cart_changed", "checkout_expired"] as const)("clears the attempt and requires a new Preview for %s", async (code) => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(preview()))
      .mockResolvedValueOnce(jsonResponse({ code, message: code, details: {} }, code === "checkout_expired" ? 410 : 409));
    renderCheckout(fetchMock);
    await screen.findByRole("button", { name: "Confirm order" });
    fireEvent.click(screen.getByRole("button", { name: "Confirm order" }));
    expect(await screen.findByText("Get a new Preview")).toBeInTheDocument();
    expect(screen.queryByTestId("checkout-recovery")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Confirm order" })).not.toBeInTheDocument();
  });

  it("keeps checkout_unavailable as a known failure without showing RESULT UNKNOWN", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(preview()))
      .mockResolvedValueOnce(jsonResponse({ code: "checkout_unavailable", message: "temporarily unavailable", details: {} }, 503));
    renderCheckout(fetchMock);
    await screen.findByRole("button", { name: "Confirm order" });
    fireEvent.click(screen.getByRole("button", { name: "Confirm order" }));
    expect(await screen.findByText("Checkout service is temporarily unavailable. You can retry this submission.")).toBeInTheDocument();
    expect(screen.queryByTestId("checkout-recovery")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry submission" })).toBeInTheDocument();
  });

  it("stops after idempotency_conflict and does not expose an automatic retry", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(preview()))
      .mockResolvedValueOnce(jsonResponse({ code: "idempotency_conflict", message: "conflict", details: {} }, 409));
    renderCheckout(fetchMock);
    await screen.findByRole("button", { name: "Confirm order" });
    fireEvent.click(screen.getByRole("button", { name: "Confirm order" }));
    expect(await screen.findByText("This submission key was already used for a different request. Start a new Preview before trying again.")).toBeInTheDocument();
    expect(screen.queryByTestId("checkout-recovery")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry submission" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Confirm order" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Get a new Preview" })).toBeInTheDocument();
  });

  it("clears mounted recovery and old identity state when the user changes", async () => {
    updateCheckoutAttempt(newCheckoutAttempt("demo-user", "user-a-token"), "unknown");
    const fetchMock = vi.fn().mockImplementation((url: string) => jsonResponse(preview({ checkout_token: url.includes("user-b") ? "user-b-token" : "user-a-token" })));
    renderCheckoutWithIdentitySwitch(fetchMock);
    expect(await screen.findByTestId("checkout-recovery")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Switch identity" }));
    await waitFor(() => expect(screen.queryByTestId("checkout-recovery")).not.toBeInTheDocument());
    expect(readCheckoutAttempt("demo-user")).toBeNull();
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("user_id=user-b"))).toBe(true);
  });
});
