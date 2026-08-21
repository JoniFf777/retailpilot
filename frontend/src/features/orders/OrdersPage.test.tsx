import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SessionProvider } from "../../app/session";
import { OrderDetailPage } from "./OrderDetailPage";
import { OrdersPage } from "./OrdersPage";

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function order(status: "pending_payment" | "cancelled" | "paid" | "expired" = "pending_payment") {
  return { order_id: "order-1", status, currency: "CNY", subtotal: { amount: "5999.00", currency: "CNY" }, total: { amount: "5999.00", currency: "CNY" }, items: [{ item_id: "item-1", sku_id: "sku-1", product_code: "NOTEBOOK", product_name: "Notebook", sku_code: "SKU-1", sku_name: "16G / 512G", unit_money: { amount: "5999.00", currency: "CNY" }, quantity: 1, subtotal_money: { amount: "5999.00", currency: "CNY" } }], version: 1, created_at: "2026-08-08T00:00:00Z", updated_at: "2026-08-08T00:00:00Z" };
}

function renderPage(element: React.ReactElement, path: string, fetchMock: ReturnType<typeof vi.fn>, routePath = path) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  vi.stubGlobal("fetch", fetchMock);
  return render(<QueryClientProvider client={queryClient}><SessionProvider><MemoryRouter initialEntries={[path]}><Routes><Route element={element} path={routePath} /></Routes></MemoryRouter></SessionProvider></QueryClientProvider>);
}

describe("Order history and snapshot detail", () => {
  beforeEach(() => { vi.restoreAllMocks(); });

  it("lists backend Order snapshots and links to detail", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ items: [order()], next_cursor: null }));
    renderPage(<OrdersPage />, "/orders", fetchMock);
    expect(await screen.findByTestId("order-list")).toHaveTextContent("order-1");
    expect(screen.getByRole("link", { name: /order-1/ })).toHaveAttribute("href", "/orders/order-1");
    expect(screen.getByText("Pending payment")).toBeInTheDocument();
  });

  it("renders a paid Order as Paid rather than Cancelled", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ items: [order("paid")], next_cursor: null }));
    renderPage(<OrdersPage />, "/orders", fetchMock);
    expect(await screen.findByTestId("order-list")).toHaveTextContent("Paid");
    expect(screen.queryByText("Cancelled")).not.toBeInTheDocument();
  });

  it("renders an expired Order without payment or cancel controls", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(order("expired")))
      .mockResolvedValueOnce(jsonResponse({ items: [] }));
    renderPage(<OrderDetailPage />, "/orders/order-1", fetchMock, "/orders/:orderId");
    await screen.findByTestId("order-detail");
    expect(screen.getByText("Expired")).toBeInTheDocument();
    expect(screen.getByTestId("payment-expired")).toHaveTextContent("Payment deadline expired");
    expect(screen.queryByRole("button", { name: "Cancel pending order" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Mock Payment" })).not.toBeInTheDocument();
  });

  it("cancels only pending Orders and does not restore or refetch Cart", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(order()))
      .mockResolvedValueOnce(jsonResponse({ items: [] }))
      .mockResolvedValueOnce(jsonResponse({ order: order("cancelled"), idempotent_replay: false }));
    renderPage(<OrderDetailPage />, "/orders/order-1", fetchMock, "/orders/:orderId");
    await screen.findByTestId("order-detail");
    fireEvent.click(screen.getByRole("button", { name: "Cancel pending order" }));
    expect(await screen.findByText("Order cancelled. Inventory was released; Cart was not restored.")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("/api/cart"))).toBe(false);
    expect(screen.getByText("cancelled")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cancel pending order" })).not.toBeInTheDocument();
  });
});
