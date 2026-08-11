import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SessionProvider } from "../../app/session";
import { ChatPage } from "./ChatPage";

function renderChat(client = new QueryClient({ defaultOptions: { mutations: { retry: false } } })) {
  render(<QueryClientProvider client={client}><SessionProvider><MemoryRouter><ChatPage /></MemoryRouter></SessionProvider></QueryClientProvider>);
  return client;
}

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

const completedResponse = { answer: "The backend recommends comparing noise and layout.", status: "completed", tool_calls: [] };
const recommendedResponse = {
  ...completedResponse,
  recommendation: {
    schema_version: "shopmind.recommendation.v1", ranking_policy_version: "v1", request_summary: "laptop", outcome: "recommended",
    structured_constraints: { memory_min_gb: 16 },
    recommendations: [{ product_id: "product-json-sse", sku_id: "sku-json-sse", product_name: "JSON / SSE 同款", sku_name: "16G", money: { amount: "5999.00", currency: "CNY" }, availability: { sale_status: "active", in_stock: true, available_quantity: 5 }, score: 90, reason: "结构化结果", score_breakdown: [], specifications: [] }],
  },
};

describe("ChatPage backend flows", () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.restoreAllMocks();
  });

  it("submits JSON chat and renders the stable response fields", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ...completedResponse, user_id: "demo-user", thread_id: "thread-test", pending_action_id: null }));
    vi.stubGlobal("fetch", fetchMock);
    renderChat();
    fireEvent.click(screen.getByTestId("json-mode-button"));
    fireEvent.change(screen.getByTestId("chat-input"), { target: { value: "Find an office keyboard" } });
    fireEvent.click(screen.getByTestId("send-button"));
    expect(await screen.findByText(completedResponse.answer)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/api/chat", expect.objectContaining({ method: "POST" }));
    const request = JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body)) as Record<string, unknown>;
    expect(request.message).toBe("Find an office keyboard");
    expect(request.thread_id).toBeTypeOf("string");
  });

  it("shows a structured retry state for a backend error", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse({ detail: "Owner data storage unavailable." }, 503)).mockResolvedValueOnce(jsonResponse({ ...completedResponse, answer: "The service recovered." }));
    vi.stubGlobal("fetch", fetchMock);
    renderChat();
    fireEvent.click(screen.getByTestId("json-mode-button"));
    fireEvent.change(screen.getByTestId("chat-input"), { target: { value: "Check headphones" } });
    fireEvent.click(screen.getByTestId("send-button"));
    expect(await screen.findByRole("alert")).toHaveTextContent("服务暂时不可用");
    fireEvent.click(screen.getByRole("button", { name: "重试" }));
    await waitFor(() => expect(screen.getByText("The service recovered.")).toBeInTheDocument());
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("connects to POST SSE and renders the terminal answer", async () => {
    const event = (sequence: number, eventType: string, payload: Record<string, unknown> = {}) => JSON.stringify({ sequence, event_type: eventType, timestamp: "2026-07-26T00:00:00Z", visibility: "client", payload });
    const fetchMock = vi.fn().mockResolvedValue(new Response([
      `event: run.started\nid: 1\ndata: ${event(1, "run.started")}\n\n`,
      `event: product.completed\nid: 2\ndata: ${event(2, "product.completed")}\n\n`,
      `event: run.result\nid: 3\ndata: ${event(3, "run.result", completedResponse)}\n\n`,
    ].join(""), { headers: { "Content-Type": "text/event-stream" } }));
    vi.stubGlobal("fetch", fetchMock);
    renderChat();
    fireEvent.change(screen.getByTestId("chat-input"), { target: { value: "Find a quiet keyboard" } });
    fireEvent.click(screen.getByTestId("send-button"));
    expect(await screen.findByText(completedResponse.answer)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/api/chat/stream", expect.objectContaining({ method: "POST" }));
  });

  it("projects the same structured recommendation from JSON and terminal SSE", async () => {
    const event = JSON.stringify({ sequence: 1, event_type: "run.result", timestamp: "2026-07-26T00:00:00Z", visibility: "client", payload: recommendedResponse });
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(recommendedResponse))
      .mockResolvedValueOnce(new Response(`event: run.result\nid: 1\ndata: ${event}\n\n`, { headers: { "Content-Type": "text/event-stream" } }));
    vi.stubGlobal("fetch", fetchMock);
    renderChat();
    fireEvent.click(screen.getByTestId("json-mode-button"));
    fireEvent.change(screen.getByTestId("chat-input"), { target: { value: "laptop json" } });
    fireEvent.click(screen.getByTestId("send-button"));
    expect(await screen.findByText("JSON / SSE 同款")).toBeInTheDocument();
    fireEvent.change(screen.getByTestId("chat-input"), { target: { value: "laptop sse" } });
    fireEvent.click(screen.getByRole("button", { name: "实时过程" }));
    fireEvent.click(screen.getByTestId("send-button"));
    await waitFor(() => expect(screen.getAllByText("JSON / SSE 同款")).toHaveLength(2));
  });

  it("confirms an add-to-cart action with exact updated arguments", async () => {
    const pending = { pending_action_id: "action-add-1", action_type: "add_to_cart", risk_class: "high", status: "pending", version: 1, expires_at: null, preview: "Pending add-to-cart action created.", editable_fields: [{ field_type: "integer", field: "quantity", label: "Quantity", current_value: 1, min_value: 1, max_value: 20, required: true }], confirm_label: "Confirm", cancel_label: "Cancel" };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ answer: "Pending add-to-cart action created.", status: "confirmation_required", tool_calls: ["prepare_add_to_cart"], pending_action_id: "action-add-1" }))
      .mockResolvedValueOnce(jsonResponse(pending))
      .mockResolvedValueOnce(jsonResponse({ answer: "Action confirmed.", status: "completed", tool_calls: ["confirm_add_to_cart"], pending_action_id: "action-add-1" }));
    vi.stubGlobal("fetch", fetchMock);
    renderChat();
    fireEvent.click(screen.getByTestId("json-mode-button"));
    fireEvent.change(screen.getByTestId("chat-input"), { target: { value: "Add TECH-KEY-010" } });
    fireEvent.click(screen.getByTestId("send-button"));
    expect(await screen.findByTestId("action-confirm")).toBeInTheDocument();
    fireEvent.change(screen.getByTestId("action-quantity"), { target: { value: "2" } });
    fireEvent.click(screen.getByTestId("action-confirm"));
    expect((await screen.findAllByText("Action confirmed.")).length).toBeGreaterThanOrEqual(1);
    const confirmCall = fetchMock.mock.calls.find((call) => String(call[0]).includes("/chat/confirm"));
    const confirmRequest = JSON.parse(String(confirmCall?.[1]?.body)) as Record<string, unknown>;
    expect(confirmRequest).toMatchObject({ pending_action_id: "action-add-1", confirmed: true, updated_arguments: { quantity: 2 } });
  });

  it("cancels a pending action through the confirmation boundary", async () => {
    const pending = { pending_action_id: "action-pref-1", action_type: "save_preference", risk_class: "medium", status: "pending", version: 1, expires_at: null, preview: "Pending preference action created.", editable_fields: [{ field_type: "enum", field: "preference_type", label: "Preference type", current_value: "other", options: ["budget", "brand", "avoid", "usage", "style", "other"], required: true }, { field_type: "text", field: "preference_value", label: "Preference value", current_value: "", min_length: 1, max_length: 2000, required: true }], confirm_label: "Confirm", cancel_label: "Cancel" };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ answer: "Pending preference action created.", status: "confirmation_required", tool_calls: ["prepare_save_preference"], pending_action_id: "action-pref-1" }))
      .mockResolvedValueOnce(jsonResponse(pending))
      .mockResolvedValueOnce(jsonResponse({ answer: "Action cancelled.", status: "cancelled", tool_calls: ["cancel_pending_action"], pending_action_id: "action-pref-1" }));
    vi.stubGlobal("fetch", fetchMock);
    renderChat();
    fireEvent.click(screen.getByTestId("json-mode-button"));
    fireEvent.change(screen.getByTestId("chat-input"), { target: { value: "Remember that I prefer blue" } });
    fireEvent.click(screen.getByTestId("send-button"));
    expect(await screen.findByTestId("action-cancel")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("action-cancel"));
    expect((await screen.findAllByText("Action cancelled.")).length).toBeGreaterThanOrEqual(1);
    const cancelCall = fetchMock.mock.calls.find((call) => String(call[0]).includes("/chat/confirm"));
    const cancelRequest = JSON.parse(String(cancelCall?.[1]?.body)) as Record<string, unknown>;
    expect(cancelRequest).toMatchObject({ pending_action_id: "action-pref-1", confirmed: false });
  });

  it("refetches ShopMind Cart after structured PendingAction confirmation without closing the drawer", async () => {
    const pending = { pending_action_id: "pa-cart-regression", action_type: "add_to_cart", risk_class: "high", status: "pending", version: 1, expires_at: null, preview: "加入回归商品", editable_fields: [{ field_type: "integer", field: "quantity", label: "数量", current_value: 1, min_value: 1, max_value: 20, required: true }], confirm_label: "确认执行", cancel_label: "取消操作" };
    const confirmed = { ...pending, status: "confirmed", version: 2 };
    const cart = { items: [{ cart_item_id: "cart-regression-1", product_id: "product-regression", product_code: "REGRESSION", product_name: "Phase 2 回归商品", sku_id: "sku-regression", sku_name: "标准版", sku_code: "REG-1", quantity: 1, unit_money: { amount: "199.00", currency: "CNY" }, subtotal_money: { amount: "199.00", currency: "CNY" }, product_sale_status: "active", sku_sale_status: "active", effective_sale_status: "active", availability: { sale_status: "active", in_stock: true, available_quantity: 5 }, created_at: "2026-08-07T00:00:00Z", updated_at: "2026-08-07T00:00:00Z", version: 1 }], item_count: 1, total_quantity: 1, subtotal: { amount: "199.00", currency: "CNY" }, currency: "CNY", warnings: [] };
    const streamEvent = JSON.stringify({ sequence: 1, event_type: "run.result", timestamp: "2026-08-07T00:00:00Z", visibility: "client", payload: { answer: "推荐回归商品", status: "completed", tool_calls: [], run_id: "run-cart-regression", recommendation_context: { source_run_id: "run-cart-regression" }, recommendation: { schema_version: "shopmind.recommendation.v1", outcome: "recommended", ranking_policy_version: "v1", request_summary: "regression", structured_constraints: {}, recommendations: [{ product_id: "product-regression", sku_id: "sku-regression", product_name: "Phase 2 回归商品", sku_name: "标准版", money: { amount: "199.00", currency: "CNY" }, availability: { sale_status: "active", in_stock: true, available_quantity: 5 }, score: 90, reason: "regression", score_breakdown: [], specifications: [] }] } } });
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url.includes("/chat/stream")) return Promise.resolve(new Response(`event: run.result\nid: 1\ndata: ${streamEvent}\n\n`, { headers: { "Content-Type": "text/event-stream" } }));
      if (url.includes("/pending-actions/add-to-cart")) return Promise.resolve(jsonResponse(pending, 201));
      if (url.includes("/pending-actions/pa-cart-regression/confirm")) return Promise.resolve(jsonResponse({ pending_action: confirmed, cart_item: null, idempotent_replay: false, requested_quantity: 1, cart_quantity: 1, price_changed: false }));
      if (url.includes("/cart")) return Promise.resolve(jsonResponse(cart));
      return Promise.resolve(jsonResponse({}));
    });
    vi.stubGlobal("fetch", fetchMock);
    renderChat();
    fireEvent.change(screen.getByTestId("chat-input"), { target: { value: "推荐回归商品" } });
    fireEvent.click(screen.getByTestId("send-button"));
    fireEvent.click(await screen.findByRole("button", { name: "选择此商品" }));
    fireEvent.change(await screen.findByTestId("action-quantity"), { target: { value: "1" } });
    fireEvent.click(await screen.findByTestId("action-confirm"));
    expect(await screen.findByText("CNY 199.00")).toBeInTheDocument();
    expect(screen.getByText("已加入购物车，共 1 件。")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some((call) => String(call[0]).includes("/api/cart"))).toBe(true);
  });
});
