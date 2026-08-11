import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SessionProvider } from "../../app/session";
import { useSession } from "../../app/useSession";
import { CartPanel } from "./CartPanel";

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function item(overrides: Record<string, unknown> = {}) {
  return {
    cart_item_id: "item-1", product_id: "product-1", product_code: "PRODUCT-1", product_name: "轻薄本", sku_id: "sku-1", sku_name: "16G / 512G", sku_code: "SKU-1", quantity: 1,
    unit_money: { amount: "5999.00", currency: "CNY" }, subtotal_money: { amount: "5999.00", currency: "CNY" }, product_sale_status: "active", sku_sale_status: "active", effective_sale_status: "active",
    availability: { sale_status: "active", in_stock: true, available_quantity: 8, reason_code: null }, created_at: "2026-08-07T00:00:00Z", updated_at: "2026-08-07T00:00:00Z", version: 1, ...overrides,
  };
}

function cart(items: Array<Record<string, unknown>> = [item()], overrides: Record<string, unknown> = {}) {
  return { items, item_count: items.length, total_quantity: items.reduce((total, value) => total + Number(value.quantity ?? 0), 0), subtotal: items.length ? { amount: "5999.00", currency: "CNY" } : null, currency: items.length ? "CNY" : null, warnings: [], ...overrides };
}

function renderCart(fetchMock: ReturnType<typeof vi.fn>) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  vi.stubGlobal("fetch", fetchMock);
  return render(<QueryClientProvider client={client}><SessionProvider><CartPanel /></SessionProvider></QueryClientProvider>);
}

function IdentityHarness() {
  const { userId, setUserId } = useSession();
  return <><button onClick={() => setUserId(userId === "demo-user" ? "user-b" : "demo-user")} type="button">切换用户</button><CartPanel /></>;
}

describe("ShopMind Cart management", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("shows loading and empty states", async () => {
    let resolve: ((value: Response) => void) | undefined;
    const fetchMock = vi.fn().mockImplementation(() => new Promise<Response>((resolvePromise) => { resolve = resolvePromise; }));
    renderCart(fetchMock);
    expect(screen.getByRole("status")).toHaveTextContent("正在读取购物车");
    resolve?.(jsonResponse(cart([])));
    expect(await screen.findByText("购物车还是空的。")).toBeInTheDocument();
  });

  it("renders summary, current prices, multiple items and backend warnings", async () => {
    const second = item({ cart_item_id: "item-2", product_name: "键盘", sku_id: "sku-2", sku_name: "静音版", sku_code: "SKU-2", quantity: 2, unit_money: { amount: "299.00", currency: "CNY" }, subtotal_money: { amount: "598.00", currency: "CNY" } });
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(cart([item(), second], { item_count: 2, total_quantity: 3, subtotal: { amount: "6597.00", currency: "CNY" } })));
    renderCart(fetchMock);
    expect(await screen.findByText("键盘")).toBeInTheDocument();
    expect(screen.getByText("商品种类").parentElement).toHaveTextContent("2");
    expect(screen.getByText("总件数").parentElement).toHaveTextContent("3");
    expect(screen.getByText("CNY 6597.00")).toBeInTheDocument();
    expect(screen.getByText("按当前商品价格计算")).toBeInTheDocument();
  });

  it("keeps mixed currency subtotal unavailable and renders warning copy", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(cart([item()], { subtotal: null, currency: null, warnings: [{ code: "mixed_currency", message: "mixed" }] })));
    renderCart(fetchMock);
    expect(await screen.findByText("当前商品小计")).toBeInTheDocument();
    expect(screen.getByText("暂不可计算")).toBeInTheDocument();
    expect(screen.getByText("购物车包含不同币种，暂不计算合计。")).toBeInTheDocument();
  });

  it("separates draft from server quantity and sends the exact PATCH request", async () => {
    let current = cart([item()]);
    const fetchMock = vi.fn().mockImplementation(async (_url: string, init?: RequestInit) => {
      if (init?.method === "PATCH") {
        expect(JSON.parse(String(init.body))).toEqual({ expected_version: 1, quantity: 3 });
        current = cart([item({ quantity: 3, subtotal_money: { amount: "17997.00", currency: "CNY" }, version: 2 })]);
        return jsonResponse({ item: current.items[0], cart: current });
      }
      return jsonResponse(current);
    });
    renderCart(fetchMock);
    const input = await screen.findByRole("textbox", { name: "轻薄本 数量" });
    fireEvent.change(input, { target: { value: "3" } });
    expect(input).toHaveValue("3");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "更新" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/cart/items/item-1", expect.objectContaining({ method: "PATCH" })));
    await waitFor(() => expect(screen.getByRole("textbox", { name: "轻薄本 数量" })).toHaveValue("3"));
    expect(document.querySelector(".cart-item-meta span")).toHaveTextContent("CNY 17997.00");
  });

  it("validates quantity locally without sending invalid values", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(cart()));
    renderCart(fetchMock);
    const input = await screen.findByRole("textbox", { name: "轻薄本 数量" });
    fireEvent.change(input, { target: { value: "21" } });
    expect(screen.getByRole("alert")).toHaveTextContent("1 到 20");
    fireEvent.click(screen.getByRole("button", { name: "更新" }));
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("keeps the draft on insufficient inventory and shows available quantity", async () => {
    const fetchMock = vi.fn().mockImplementation(async (_url: string, init?: RequestInit) => init?.method === "PATCH"
      ? jsonResponse({ code: "insufficient_inventory", message: "short", details: { available_quantity: 2 } }, 409)
      : jsonResponse(cart()));
    renderCart(fetchMock);
    const input = await screen.findByRole("textbox", { name: "轻薄本 数量" });
    fireEvent.change(input, { target: { value: "4" } });
    fireEvent.click(screen.getByRole("button", { name: "更新" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("当前库存最多可支持 2 件");
    expect(screen.getByRole("textbox", { name: "轻薄本 数量" })).toHaveValue("4");
  });

  it("refetches latest quantity and version after a version conflict", async () => {
    let getCount = 0;
    const latest = cart([item({ quantity: 2, version: 2, subtotal_money: { amount: "11998.00", currency: "CNY" } })]);
    const fetchMock = vi.fn().mockImplementation(async (_url: string, init?: RequestInit) => {
      if (init?.method === "PATCH") return jsonResponse({ code: "cart_version_conflict", message: "conflict", details: { current_version: 2 } }, 409);
      getCount += 1;
      return jsonResponse(getCount === 1 ? cart() : latest);
    });
    renderCart(fetchMock);
    const input = await screen.findByRole("textbox", { name: "轻薄本 数量" });
    fireEvent.change(input, { target: { value: "3" } });
    fireEvent.click(screen.getByRole("button", { name: "更新" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("已为你刷新最新状态");
    expect(screen.getByRole("textbox", { name: "轻薄本 数量" })).toHaveValue("2");
    expect(getCount).toBe(2);
  });

  it("keeps unavailable items visible, disables quantity edits and enables delete", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(cart([item({ effective_sale_status: "inactive", product_sale_status: "inactive", availability: { sale_status: "inactive", in_stock: false, available_quantity: 0, reason_code: "out_of_stock" } })], { warnings: [{ code: "product_inactive", cart_item_id: "item-1", sku_id: "sku-1", message: "inactive" }, { code: "out_of_stock", cart_item_id: "item-1", sku_id: "sku-1", message: "out" }] })));
    renderCart(fetchMock);
    const input = await screen.findByRole("textbox", { name: "轻薄本 数量" });
    expect(input).toBeDisabled();
    expect(screen.getByRole("button", { name: "删除" })).toBeEnabled();
    expect(screen.getByText("商品已不可购买，但仍保留在购物车中。")).toBeInTheDocument();
  });

  it("confirms item deletion, handles 204, and refetches the empty Cart", async () => {
    let deleted = false;
    const fetchMock = vi.fn().mockImplementation(async (_url: string, init?: RequestInit) => {
      if (init?.method === "DELETE") { deleted = true; return new Response(null, { status: 204 }); }
      return jsonResponse(deleted ? cart([]) : cart());
    });
    renderCart(fetchMock);
    await screen.findByText("轻薄本");
    fireEvent.click(screen.getByRole("button", { name: "删除" }));
    expect(screen.getByRole("dialog")).toHaveTextContent("从购物车移除“轻薄本”？");
    fireEvent.click(screen.getByRole("button", { name: "取消" }));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "删除" }));
    fireEvent.click(screen.getByRole("button", { name: "确认移除" }));
    expect(await screen.findByText("购物车还是空的。")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some((call) => call[1]?.method === "DELETE")).toBe(true);
  });

  it("confirms clearing the Cart and does not expose checkout controls", async () => {
    let cleared = false;
    const fetchMock = vi.fn().mockImplementation(async (_url: string, init?: RequestInit) => {
      if (init?.method === "DELETE") { cleared = true; return new Response(null, { status: 204 }); }
      return jsonResponse(cleared ? cart([]) : cart());
    });
    renderCart(fetchMock);
    await screen.findByText("轻薄本");
    fireEvent.click(screen.getByRole("button", { name: "清空购物车" }));
    expect(screen.getByRole("dialog")).toHaveTextContent("确定清空 ShopMind 购物车吗？");
    fireEvent.click(screen.getByRole("button", { name: "确认清空" }));
    expect(await screen.findByText("购物车还是空的。")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /结算|支付|订单/ })).not.toBeInTheDocument();
  });

  it("clears the old development user's Cart before showing the new identity", async () => {
    const fetchMock = vi.fn().mockImplementation((url: string) => url.includes("user-b")
      ? Promise.resolve(jsonResponse(cart([item({ product_name: "用户 B 商品" })])))
      : Promise.resolve(jsonResponse(cart([item({ product_name: "用户 A 商品" })]))));
    vi.stubGlobal("fetch", fetchMock);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><SessionProvider><IdentityHarness /></SessionProvider></QueryClientProvider>);
    expect(await screen.findByText("用户 A 商品")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "切换用户" }));
    expect(await screen.findByText("用户 B 商品")).toBeInTheDocument();
    expect(screen.queryByText("用户 A 商品")).not.toBeInTheDocument();
  });
});
