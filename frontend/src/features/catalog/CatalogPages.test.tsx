import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { SessionProvider } from "../../app/session";
import { CatalogCategoryPage, CatalogHomePage, CatalogProductDetailPage } from "./CatalogPages";

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const categoryItems = [
  { code: "phone", display_name: "手机", product_count: 9, available_product_count: 8 },
  { code: "keyboard", display_name: "键盘", product_count: 9, available_product_count: 9 },
  { code: "router", display_name: "路由器", product_count: 9, available_product_count: 9 },
];

function product(code: string, displayName: string) {
  return {
    product_id: `${code}-product`,
    product_code: `${code.toUpperCase()}-001`,
    brand: "Test Brand",
    name: `${displayName} 示例`,
    category: { code, display_name: displayName, product_count: 1, available_product_count: 1 },
    specifications: [
      {
        key: "metric",
        label: "核心规格",
        value: 42,
        value_type: "number",
        unit: "单位",
        display_order: 10,
        comparable: true,
        format_hint: null,
      },
    ],
    skus: [
      {
        sku_id: `${code}-sku`,
        sku_code: `${code.toUpperCase()}-SKU-001`,
        sku_name: "标准版",
        money: { amount: "199.00", currency: "CNY" },
        availability: {
          sale_status: "active",
          available_quantity: 4,
          in_stock: true,
          reason_code: null,
        },
        variant_specifications: [],
      },
    ],
  };
}

function renderPage(element: ReactNode, route: string) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <SessionProvider>
        <MemoryRouter initialEntries={[route]}>{element}</MemoryRouter>
      </SessionProvider>
    </QueryClientProvider>,
  );
}

describe("Catalog browse pages", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("discovers categories from the API", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ items: categoryItems }));
    vi.stubGlobal("fetch", fetchMock);
    renderPage(<CatalogHomePage />, "/catalog");
    expect(await screen.findByRole("heading", { name: "浏览商品" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /手机/ })).toHaveAttribute("href", "/catalog/phone");
    expect(screen.getByRole("link", { name: /键盘/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /路由器/ })).toBeInTheDocument();
  });

  it.each([
    ["phone", "手机"],
    ["keyboard", "键盘"],
    ["router", "路由器"],
  ])("uses one generic list renderer for %s", async (code, displayName) => {
    const item = product(code, displayName);
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        jsonResponse({ category: item.category, items: [item], total: 1, limit: 100, offset: 0 }),
      );
    vi.stubGlobal("fetch", fetchMock);
    renderPage(
      <Routes>
        <Route element={<CatalogCategoryPage />} path="/catalog/:category" />
      </Routes>,
      `/catalog/${code}`,
    );
    expect(await screen.findByRole("heading", { name: displayName })).toBeInTheDocument();
    expect(screen.getByText("核心规格")).toBeInTheDocument();
    expect(screen.getByText("CNY 199.00")).toBeInTheDocument();
  });

  it("renders detail and routes browse add-to-cart through PendingAction confirmation", async () => {
    const item = product("router", "路由器");
    const action = {
      pending_action_id: "action-1",
      action_type: "add_to_cart",
      risk_class: "high",
      status: "pending",
      version: 1,
      expires_at: null,
      preview: {
        kind: "catalog_sku",
        sku_id: "router-sku",
        sku_code: "ROUTER-SKU-001",
        product_id: "router-product",
        product_code: "ROUTER-001",
        product_name: "路由器 示例",
        sku_name: "标准版",
        requested_quantity: 1,
        unit_money_snapshot: { amount: "199.00", currency: "CNY" },
        subtotal_money_snapshot: { amount: "199.00", currency: "CNY" },
        availability_snapshot: {
          sale_status: "active",
          available_quantity: 4,
          in_stock: true,
          reason_code: null,
        },
        preview_text: "preview",
      },
      editable_fields: [
        {
          field_type: "integer",
          field: "quantity",
          label: "数量",
          current_value: 1,
          min_value: 1,
          max_value: 20,
          required: true,
        },
      ],
      confirm_label: "Confirm",
      cancel_label: "Cancel",
    };
    const confirmed = {
      pending_action: { ...action, status: "confirmed", editable_fields: [] },
      cart_item: { sku_id: "router-sku" },
      price_changed: false,
      requested_quantity: 1,
      cart_quantity: 1,
      idempotent_replay: false,
    };
    const fetchMock = vi.fn().mockImplementation(async (url: string, init?: RequestInit) => {
      if (init?.method === "POST" && url === "/api/pending-actions/catalog-add-to-cart")
        return jsonResponse(action, 201);
      if (init?.method === "POST" && url === "/api/pending-actions/action-1/confirm")
        return jsonResponse(confirmed);
      return jsonResponse(item);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderPage(
      <Routes>
        <Route element={<CatalogProductDetailPage />} path="/catalog/:category/:product" />
      </Routes>,
      "/catalog/router/ROUTER-001",
    );
    expect(await screen.findByRole("heading", { name: "路由器 示例" })).toBeInTheDocument();
    expect(screen.getByText("核心规格")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "加入购物车" }));
    expect(await screen.findByRole("dialog")).toHaveTextContent("路由器 示例");
    fireEvent.click(screen.getByRole("button", { name: "确认执行" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("已加入购物车"));
    expect(
      fetchMock.mock.calls.some(([url, init]) => url === "/api/cart" || init?.method === "PATCH"),
    ).toBe(false);
  });
});
