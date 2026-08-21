import { expect, test, type Page, type Route } from "@playwright/test";

const streamEvent = (eventType: string, sequence: number, payload: Record<string, unknown> = {}) => [
  `event: ${eventType}`,
  `id: ${sequence}`,
  `data: ${JSON.stringify({ sequence, event_type: eventType, timestamp: "2026-07-26T00:00:00Z", agent_name: "e2e", trace_id: "trace-e2e", visibility: "client", payload })}`,
  "",
].join("\n");

test("chat critical path consumes POST SSE and renders the terminal answer", async ({ page }) => {
  await page.route("**/api/chat/stream", async (route) => {
    const body = [
      streamEvent("run.started", 1),
      streamEvent("run.result", 2, { answer: "E2E mock answer", status: "completed", tool_calls: [], thread_id: "thread-e2e", run_id: "run-e2e", trace_id: "trace-e2e" }),
    ].join("\n");
    await route.fulfill({ status: 200, headers: { "Content-Type": "text/event-stream" }, body });
  });

  await page.goto("/");
  await page.getByTestId("chat-input").fill("帮我找一款适合办公的键盘");
  await page.getByTestId("send-button").click();

  await expect(page.getByTestId("message-list")).toContainText("E2E mock answer");
  await expect(page.getByTestId("chat-input")).toHaveValue("");
  await expect(page.getByTestId("send-button")).toBeDisabled();
});

test("status critical path renders a sanitized blocked readiness report", async ({ page }) => {
  await page.route("**/api/health", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok" }) });
  });
  await page.route("**/api/health/readiness", async (route) => {
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ schema_version: "shopmind.deployment-readiness.v1", profile: "development", status: "blocked", ready: false, total_checks: 1, passed_checks: 0, failed_checks: 1, not_applicable_checks: 0, checks: [{ check_id: "postgres.connectivity", category: "database", status: "failed", reason: "postgres_unavailable" }] }),
    });
  });

  await page.goto("/status");
  await expect(page.getByText("blocked")).toBeVisible();
  await expect(page.getByText("postgres.connectivity")).toBeVisible();
  await expect(page.getByText("postgres_unavailable")).toBeVisible();
});

function recommendation(skuId: string, name: string, score: number, alternative_skus: Record<string, unknown>[] = []) {
  return { product_id: `product-${skuId}`, sku_id: skuId, product_name: name, sku_name: `${name} SKU`, money: { amount: `${5000 + score}.00`, currency: "CNY" }, availability: { sale_status: "active", available_quantity: 8, in_stock: true }, score, reason: "满足结构化条件", score_breakdown: [], specifications: [{ code: "memory", name: "内存", value: 16, value_type: "integer", unit: "GB", comparable: true, display_order: 1 }], alternative_skus };
}

test("recommended SSE renders three cards, compares four SKUs, and restores focus", async ({ page }) => {
  const alternative = { sku_id: "sku-alt", sku_code: "ALT", sku_name: "同款 32G", money: { amount: "6999.00", currency: "CNY" }, availability: { sale_status: "active", available_quantity: 2, in_stock: true }, differing_specifications: [{ code: "memory", name: "内存", value: 32, value_type: "integer", unit: "GB", comparable: true, display_order: 1 }] };
  await page.route("**/api/chat/stream", async (route) => await route.fulfill({ status: 200, headers: { "Content-Type": "text/event-stream" }, body: [streamEvent("run.result", 1, { answer: "推荐三款", status: "completed", tool_calls: [], recommendation: { schema_version: "shopmind.recommendation.v1", outcome: "recommended", ranking_policy_version: "v1", request_summary: "开发", structured_constraints: {}, recommendations: [recommendation("sku-1", "笔记本 A", 91, [alternative]), recommendation("sku-2", "笔记本 B", 88), recommendation("sku-3", "笔记本 C", 84)] } })].join("\n") }));
  await page.goto("/");
  await page.getByTestId("chat-input").fill("预算 6000 元以内的开发本");
  await page.getByTestId("send-button").click();
  await expect(page.locator(".recommendation-card")).toHaveCount(3);
  await page.locator(".recommendation-card").nth(0).locator(".compare-button").click();
  await page.locator(".alternative-item").getByRole("button", { name: "加入对比" }).click();
  await page.locator(".recommendation-card").nth(1).locator(".compare-button").click();
  await page.locator(".recommendation-card").nth(2).locator(".compare-button").click();
  const compare = page.getByRole("button", { name: "对比已选（4）" });
  await compare.click();
  await expect(page.getByRole("dialog", { name: "SKU 对比" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(compare).toBeFocused();
});

test("no_match only fills the draft when adjusting requirements", async ({ page }) => {
  await page.route("**/api/chat/stream", async (route) => await route.fulfill({ status: 200, headers: { "Content-Type": "text/event-stream" }, body: streamEvent("run.result", 1, { answer: "暂时没有匹配", status: "completed", tool_calls: [], recommendation: { schema_version: "shopmind.recommendation.v1", outcome: "no_match", ranking_policy_version: "v1", request_summary: "开发", structured_constraints: {}, no_match_reason: "预算不足", recommendations: [] } }) }));
  await page.goto("/");
  await page.getByTestId("chat-input").fill("找一台本");
  await page.getByTestId("send-button").click();
  await expect(page.getByText("预算不足")).toBeVisible();
  await page.getByRole("button", { name: "调整需求" }).click();
  await expect(page.getByTestId("chat-input")).toHaveValue("我可以调整预算、用途、内存或重量要求：");
});

test("clarification_required shows missing fields and does not auto-submit", async ({ page }) => {
  await page.route("**/api/chat/stream", async (route) => await route.fulfill({ status: 200, headers: { "Content-Type": "text/event-stream" }, body: streamEvent("run.result", 1, { answer: "需要更多信息", status: "completed", tool_calls: [], recommendation: { schema_version: "shopmind.recommendation.v1", outcome: "clarification_required", ranking_policy_version: "v1", request_summary: "开发", structured_constraints: {}, missing_fields: ["用途"], clarification_question: "请补充主要用途", recommendations: [] } }) }));
  await page.goto("/");
  await page.getByTestId("chat-input").fill("我想买笔记本");
  await page.getByTestId("send-button").click();
  await expect(page.getByText("请补充主要用途")).toBeVisible();
  await expect(page.getByText("待补充：用途")).toBeVisible();
  await page.getByRole("button", { name: "补充信息" }).click();
  await expect(page.getByTestId("chat-input")).toHaveValue("请补充主要用途");
});

test("legacy plain-text response has no recommendation panel", async ({ page }) => {
  await page.route("**/api/chat/stream", async (route) => await route.fulfill({ status: 200, headers: { "Content-Type": "text/event-stream" }, body: streamEvent("run.result", 1, { answer: "TECH-LAP-001 价格为 5999 元", status: "completed", tool_calls: [] }) }));
  await page.goto("/");
  await page.getByTestId("chat-input").fill("TECH-LAP-001 多少钱？");
  await page.getByTestId("send-button").click();
  await expect(page.getByText("TECH-LAP-001 价格为 5999 元")).toBeVisible();
  await expect(page.locator(".recommendation-panel")).toHaveCount(0);
});

test("confirmation action sends the exact confirm payload", async ({ page }) => {
  let confirmPayload: Record<string, unknown> | null = null;
  await page.route("**/api/chat", async (route) => await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ answer: "请确认加入购物车", status: "confirmation_required", tool_calls: ["prepare_add_to_cart"], pending_action_id: "action-e2e" }) }));
  await page.route("**/api/pending-actions/action-e2e**", async (route) => await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ pending_action_id: "action-e2e", action_type: "add_to_cart", risk_class: "high", status: "pending", version: 1, expires_at: null, preview: { product_name: "E2E 商品", sku_name: "标准版", sku_code: "TECH-LAP-001", requested_quantity: 1, unit_money_snapshot: { amount: "5999.00", currency: "CNY" }, availability_snapshot: { sale_status: "active", in_stock: true, available_quantity: 8 } }, editable_fields: [{ field_type: "integer", field: "quantity", label: "数量", current_value: 1, min_value: 1, max_value: 20, required: true }], confirm_label: "确认执行", cancel_label: "取消操作" }) }));
  await page.route("**/api/chat/confirm", async (route) => { confirmPayload = JSON.parse(route.request().postData() ?? "{}"); await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ answer: "已取消", status: "cancelled", tool_calls: ["cancel_pending_action"], pending_action_id: "action-e2e" }) }); });
  await page.goto("/");
  await page.getByTestId("json-mode-button").click();
  await page.getByTestId("chat-input").fill("添加 TECH-LAP-001");
  await page.getByTestId("send-button").click();
  await expect(page.getByTestId("action-cancel")).toBeVisible();
  await page.getByTestId("action-cancel").click();
  await expect.poll(() => confirmPayload).toMatchObject({ confirmed: false, pending_action_id: "action-e2e" });
});

test("structured SKU selection uses typed pending-action endpoints and refreshes the cart", async ({ page }) => {
  let createPayload: Record<string, unknown> | null = null;
  let confirmPayload: Record<string, unknown> | null = null;
  await page.route("**/api/chat/stream", async (route) => {
    const payload = { answer: "推荐一款笔记本", status: "completed", tool_calls: [], run_id: "run-structured", recommendation_context: { source_run_id: "run-structured" }, recommendation: { schema_version: "shopmind.recommendation.v1", outcome: "recommended", ranking_policy_version: "v1", request_summary: "laptop", structured_constraints: {}, recommendations: [recommendation("sku-structured", "结构化笔记本", 95)] } };
    await route.fulfill({ status: 200, headers: { "Content-Type": "text/event-stream" }, body: streamEvent("run.result", 1, payload) });
  });
  await page.route("**/api/pending-actions/add-to-cart", async (route) => { createPayload = JSON.parse(route.request().postData() ?? "{}"); await route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ pending_action_id: "pa-structured", action_type: "add_to_cart", risk_class: "high", status: "pending", version: 1, expires_at: null, preview: { product_name: "结构化笔记本", sku_name: "结构化笔记本 SKU", sku_id: "sku-structured", quantity: 1, unit_money: { amount: "5095.00", currency: "CNY" }, subtotal_money: { amount: "5095.00", currency: "CNY" }, availability: { sale_status: "active", in_stock: true, available_quantity: 8 } }, editable_fields: [{ field_type: "integer", field: "quantity", label: "数量", current_value: 1, min_value: 1, max_value: 20, required: true }], confirm_label: "确认执行", cancel_label: "取消操作" }) }); });
  await page.route("**/api/pending-actions/pa-structured/confirm", async (route) => { confirmPayload = JSON.parse(route.request().postData() ?? "{}"); await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ pending_action: { pending_action_id: "pa-structured", action_type: "add_to_cart", risk_class: "high", status: "confirmed", version: 2, expires_at: null, preview: {}, editable_fields: [] }, cart_item: { cart_item_id: "cart-1", product_id: "p-s", sku_id: "sku-structured", product_name: "结构化笔记本", sku_name: "结构化笔记本 SKU", sku_code: "SKU-S", quantity: 1, unit_money: { amount: "5095.00", currency: "CNY" }, subtotal_money: { amount: "5095.00", currency: "CNY" }, effective_sale_status: "active", availability: { sale_status: "active", in_stock: true, available_quantity: 7 }, inventory_version: 2 }, idempotent_replay: false, resolution: { requested_quantity: 1, cart_quantity: 1, price_changed: false } }) }); });
  await page.route("**/api/cart**", async (route) => await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [], total_money: { amount: "0.00", currency: "CNY" } }) }));
  await page.goto("/");
  await page.getByTestId("chat-input").fill("推荐一台开发本");
  await page.getByTestId("send-button").click();
  await page.getByRole("button", { name: "选择此商品" }).click();
  await expect(page.getByTestId("action-confirm")).toBeVisible();
  await page.getByTestId("action-quantity").fill("2");
  await page.getByTestId("action-confirm").click();
  await expect.poll(() => createPayload).toMatchObject({ thread_id: expect.any(String), source_run_id: "run-structured", sku_id: "sku-structured", quantity: 1 });
  await expect.poll(() => confirmPayload).toMatchObject({ thread_id: expect.any(String), expected_version: 1, updated_fields: { quantity: 2 } });
  await expect(page.getByText("ShopMind 购物车", { exact: true })).toBeVisible();
});

type CartItemFixture = Record<string, unknown>;

function cartItemFixture(overrides: CartItemFixture = {}): CartItemFixture {
  return { cart_item_id: "cart-e2e-1", product_id: "product-e2e-1", product_code: "E2E-1", product_name: "E2E 商品", sku_id: "sku-e2e-1", sku_name: "标准版", sku_code: "E2E-SKU-1", quantity: 1, unit_money: { amount: "5999.00", currency: "CNY" }, subtotal_money: { amount: "5999.00", currency: "CNY" }, product_sale_status: "active", sku_sale_status: "active", effective_sale_status: "active", availability: { sale_status: "active", in_stock: true, available_quantity: 8 }, created_at: "2026-08-07T00:00:00Z", updated_at: "2026-08-07T00:00:00Z", version: 1, ...overrides };
}

function cartFixture(item: CartItemFixture = cartItemFixture()): CartItemFixture {
  return { items: [item], item_count: 1, total_quantity: item.quantity, subtotal: item.subtotal_money, currency: "CNY", warnings: [] };
}

async function openManagedCart(page: Page, initialCart: CartItemFixture, handlers: { get?: () => CartItemFixture; patch?: (route: Route) => Promise<void>; delete?: (route: Route) => Promise<void> } = {}) {
  await page.route("**/api/chat/stream", async (route) => {
    const payload = { answer: "推荐 E2E 商品", status: "completed", tool_calls: [], run_id: "run-cart-e2e", recommendation_context: { source_run_id: "run-cart-e2e" }, recommendation: { schema_version: "shopmind.recommendation.v1", outcome: "recommended", ranking_policy_version: "v1", request_summary: "cart", structured_constraints: {}, recommendations: [recommendation("sku-e2e-1", "E2E 商品", 95)] } };
    await route.fulfill({ status: 200, headers: { "Content-Type": "text/event-stream" }, body: streamEvent("run.result", 1, payload) });
  });
  await page.route("**/api/pending-actions/add-to-cart", async (route) => await route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ pending_action_id: "pa-cart-e2e", action_type: "add_to_cart", risk_class: "high", status: "pending", version: 1, expires_at: null, preview: {}, editable_fields: [{ field_type: "integer", field: "quantity", label: "数量", current_value: 1, min_value: 1, max_value: 20, required: true }], confirm_label: "确认执行", cancel_label: "取消操作" }) }));
  await page.route("**/api/pending-actions/pa-cart-e2e/confirm", async (route) => await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ pending_action: { pending_action_id: "pa-cart-e2e", action_type: "add_to_cart", risk_class: "high", status: "confirmed", version: 2, expires_at: null, preview: {}, editable_fields: [] }, cart_item: null, idempotent_replay: false, requested_quantity: 1, cart_quantity: 1, price_changed: false }) }));
  await page.route("**/api/cart**", async (route) => {
    const request = route.request();
    if (request.method() === "PATCH" && handlers.patch) return handlers.patch(route);
    if (request.method() === "DELETE" && request.url().includes("/items/") && handlers.delete) return handlers.delete(route);
    if (request.method() === "DELETE" && handlers.delete) return handlers.delete(route);
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(handlers.get ? handlers.get() : initialCart) });
  });
  await page.goto("/");
  await page.getByTestId("chat-input").fill("推荐 E2E 商品");
  await page.getByTestId("send-button").click();
  await page.getByRole("button", { name: "选择此商品" }).click();
  await page.getByTestId("action-quantity").fill("1");
  await page.getByTestId("action-confirm").click();
  await expect(page.getByText("ShopMind 购物车", { exact: true })).toBeVisible();
}

function checkoutPreviewFixture(overrides: Record<string, unknown> = {}) {
  return { items: [{ cart_item_id: "cart-e2e-1", sku_id: "sku-e2e-1", product_name: "E2E Product", sku_name: "Standard", quantity: 1, unit_money: { amount: "5999.00", currency: "CNY" }, subtotal_money: { amount: "5999.00", currency: "CNY" }, availability: { sale_status: "active", in_stock: true, available_quantity: 8 }, version: 1 }], item_count: 1, total_quantity: 1, subtotal: { amount: "5999.00", currency: "CNY" }, currency: "CNY", warnings: [], can_create_order: true, checkout_token: "checkout-e2e-token", expires_at: "2026-08-08T00:10:00Z", revalidation_required: true, ...overrides };
}

function orderFixture() {
  return { order_id: "order-e2e-1", status: "pending_payment", currency: "CNY", subtotal: { amount: "5999.00", currency: "CNY" }, total: { amount: "5999.00", currency: "CNY" }, items: [{ item_id: "order-item-e2e-1", sku_id: "sku-e2e-1", product_code: "E2E-1", product_name: "E2E Product", sku_code: "E2E-SKU-1", sku_name: "Standard", unit_money: { amount: "5999.00", currency: "CNY" }, quantity: 1, subtotal_money: { amount: "5999.00", currency: "CNY" } }], version: 1, created_at: "2026-08-08T00:00:00Z", updated_at: "2026-08-08T00:00:00Z" };
}

test("Cart Go checkout only navigates to Preview and never creates an Order", async ({ page }) => {
  await openManagedCart(page, cartFixture());
  let createCalls = 0;
  await page.route("**/api/checkout/preview**", async (route) => await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(checkoutPreviewFixture()) }));
  await page.route("**/api/orders**", async (route) => { createCalls += 1; await route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ code: "unexpected", message: "unexpected" }) }); });
  await page.locator(".cart-checkout-button").click();
  await expect(page).toHaveURL(/\/checkout$/);
  await expect(page.getByTestId("checkout-preview")).toContainText("E2E Product");
  expect(createCalls).toBe(0);
});

test("explicit Confirm creates one pending-payment Order with one stable key", async ({ page }) => {
  const keys: string[] = [];
  let createCalls = 0;
  await page.route("**/api/checkout/preview**", async (route) => await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(checkoutPreviewFixture()) }));
  await page.route("**/api/orders**", async (route) => {
    if (route.request().method() !== "POST") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [], next_cursor: null }) });
    createCalls += 1;
    keys.push(route.request().headers()["idempotency-key"] ?? "");
    await route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ order: orderFixture(), idempotent_replay: false }) });
  });
  await page.goto("/checkout");
  await page.getByRole("button", { name: "Confirm order" }).dblclick();
  await expect(page.getByTestId("order-confirmation")).toBeVisible();
  expect(createCalls).toBe(1);
  expect(keys[0]).toMatch(/^request-/);
  expect(new Set(keys).size).toBe(1);
});

test("response-lost Order creation retries with the original key", async ({ page }) => {
  const keys: string[] = [];
  let createCalls = 0;
  await page.route("**/api/checkout/preview**", async (route) => await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(checkoutPreviewFixture()) }));
  await page.route("**/api/orders**", async (route) => {
    if (route.request().method() !== "POST") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [], next_cursor: null }) });
    createCalls += 1;
    keys.push(route.request().headers()["idempotency-key"] ?? "");
    if (createCalls === 1) return route.abort();
    await route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ order: orderFixture(), idempotent_replay: false }) });
  });
  await page.goto("/checkout");
  await page.getByRole("button", { name: "Confirm order" }).click();
  await expect(page.getByTestId("checkout-recovery")).toBeVisible();
  await page.getByTestId("checkout-recovery").getByRole("button", { name: "Retry submission" }).click();
  await expect(page.getByTestId("order-confirmation")).toBeVisible();
  expect(createCalls).toBe(2);
  expect(keys[0]).toBe(keys[1]);
});

test("Orders list, snapshot detail, and pending cancellation do not repopulate Cart", async ({ page }) => {
  let cartCalls = 0;
  await page.route("**/api/cart**", async (route) => { cartCalls += 1; await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(cartFixture()) }); });
  await page.route("**/api/orders**", async (route) => {
    const request = route.request();
    if (request.method() === "POST" && request.url().includes("/cancel")) return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ order: { ...orderFixture(), status: "cancelled" }, idempotent_replay: false }) });
    if (request.method() === "GET" && request.url().includes("/order-e2e-1")) return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(orderFixture()) });
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [orderFixture()], next_cursor: null }) });
  });
  await page.goto("/orders");
  await expect(page.getByTestId("order-list")).toContainText("order-e2e-1");
  await page.getByRole("link", { name: /order-e2e-1/ }).click();
  await expect(page.getByTestId("order-detail")).toContainText("E2E Product");
  await page.getByRole("button", { name: "Cancel pending order" }).click();
  await expect(page.getByText("Order cancelled. Inventory was released; Cart was not restored.")).toBeVisible();
  expect(cartCalls).toBe(0);
});

test("price_changed blocks silent resubmit and requires a fresh Preview", async ({ page }) => {
  let previewCalls = 0;
  let createCalls = 0;
  await page.route("**/api/checkout/preview**", async (route) => {
    previewCalls += 1;
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(checkoutPreviewFixture({ checkout_token: `checkout-price-${previewCalls}` })) });
  });
  await page.route("**/api/orders**", async (route) => {
    if (route.request().method() !== "POST") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [], next_cursor: null }) });
    createCalls += 1;
    await route.fulfill({ status: 409, contentType: "application/json", body: JSON.stringify({ code: "price_changed", message: "Price changed", details: {} }) });
  });
  await page.goto("/checkout");
  await page.getByRole("button", { name: "Confirm order" }).click();
  await expect(page.getByRole("button", { name: "Get a new Preview" })).toBeVisible();
  expect(createCalls).toBe(1);
  const callsBeforeNewPreview = previewCalls;
  await page.getByRole("button", { name: "Get a new Preview" }).click();
  await expect(page.getByRole("button", { name: "Confirm order" })).toBeVisible();
  expect(previewCalls).toBeGreaterThan(callsBeforeNewPreview);
});

test("cart_changed requires a new Preview before another Create request", async ({ page }) => {
  let createCalls = 0;
  await page.route("**/api/checkout/preview**", async (route) => await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(checkoutPreviewFixture()) }));
  await page.route("**/api/orders**", async (route) => {
    if (route.request().method() !== "POST") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [], next_cursor: null }) });
    createCalls += 1;
    await route.fulfill({ status: 409, contentType: "application/json", body: JSON.stringify({ code: "cart_changed", message: "Cart changed", details: {} }) });
  });
  await page.goto("/checkout");
  await page.getByRole("button", { name: "Confirm order" }).click();
  await expect(page.getByRole("button", { name: "Get a new Preview" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Confirm order" })).not.toBeVisible();
  expect(createCalls).toBe(1);
});

test("Checkout Preview with insufficient inventory keeps Confirm unavailable", async ({ page }) => {
  await page.route("**/api/checkout/preview**", async (route) => await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(checkoutPreviewFixture({ can_create_order: false, checkout_token: null, warnings: [{ code: "insufficient_inventory", cart_item_id: "cart-e2e-1", sku_id: "sku-e2e-1", message: "Only 0 available" }] })) }));
  await page.goto("/checkout");
  await expect(page.getByTestId("checkout-preview")).toContainText("Only 0 available");
  await expect(page.getByRole("button", { name: "Confirm order" })).not.toBeVisible();
});

test("switching identity after an unknown result does not expose the previous Checkout attempt", async ({ page }) => {
  await page.route("**/api/checkout/preview**", async (route) => await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(checkoutPreviewFixture({ checkout_token: "user-b-checkout" })) }));
  await page.route("**/api/orders**", async (route) => route.abort());
  await page.goto("/checkout");
  await page.getByRole("button", { name: "Confirm order" }).click();
  await expect(page.getByTestId("checkout-recovery")).toBeVisible();
  await page.goto("/");
  await page.locator("#dev-user-id").fill("user-b");
  await page.goto("/checkout");
  await expect(page.getByTestId("checkout-preview")).toBeVisible();
  await expect(page.getByTestId("checkout-recovery")).not.toBeVisible();
  await expect(page.getByRole("button", { name: "Confirm order" })).toBeVisible();
});

test("Cart quantity success sends expected_version and updates summary", async ({ page }) => {
  let patchBody: Record<string, unknown> | null = null;
  let current = cartFixture();
  const updated = cartItemFixture({ quantity: 3, version: 2, subtotal_money: { amount: "17997.00", currency: "CNY" } });
  await openManagedCart(page, current, { get: () => current, patch: async (route) => { patchBody = JSON.parse(route.request().postData() ?? "{}"); current = cartFixture(updated); await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ item: updated, cart: current }) }); } });
  await page.getByRole("textbox", { name: "E2E 商品 数量" }).fill("3");
  await page.getByRole("button", { name: "更新" }).click();
  await expect.poll(() => patchBody).toEqual({ expected_version: 1, quantity: 3 });
  await expect(page.locator(".cart-item-meta")).toContainText("CNY 17997.00");
});

test("Cart insufficient inventory preserves the draft quantity", async ({ page }) => {
  await openManagedCart(page, cartFixture(), { patch: async (route) => await route.fulfill({ status: 409, contentType: "application/json", body: JSON.stringify({ code: "insufficient_inventory", message: "short", details: { available_quantity: 2 } }) }) });
  const input = page.getByRole("textbox", { name: "E2E 商品 数量" });
  await input.fill("4");
  await page.getByRole("button", { name: "更新" }).click();
  await expect(page.getByRole("alert")).toContainText("当前库存最多可支持 2 件");
  await expect(input).toHaveValue("4");
});

test("Cart version conflict refetches the latest server quantity", async ({ page }) => {
  const latest = cartItemFixture({ quantity: 2, version: 2, subtotal_money: { amount: "11998.00", currency: "CNY" } });
  let getCount = 0;
  await openManagedCart(page, cartFixture(), { get: () => { getCount += 1; return getCount > 1 ? cartFixture(latest) : cartFixture(); }, patch: async (route) => { await route.fulfill({ status: 409, contentType: "application/json", body: JSON.stringify({ code: "cart_version_conflict", message: "conflict", details: { current_version: 2 } }) }); } });
  const input = page.getByRole("textbox", { name: "E2E 商品 数量" });
  await input.fill("3");
  await page.getByRole("button", { name: "更新" }).click();
  await expect(page.getByRole("alert")).toContainText("已为你刷新最新状态");
  await expect(input).toHaveValue("2");
});

test("Cart item delete confirms, sends DELETE and renders empty Cart", async ({ page }) => {
  let deleted = false;
  await openManagedCart(page, cartFixture(), { get: () => deleted ? { items: [], item_count: 0, total_quantity: 0, subtotal: null, currency: null, warnings: [] } : cartFixture(), delete: async (route) => { deleted = true; await route.fulfill({ status: 204 }); } });
  await page.getByRole("button", { name: "删除" }).click();
  await expect(page.getByRole("dialog", { name: "移除购物车商品" })).toContainText("从购物车移除“E2E 商品”？");
  await page.getByRole("button", { name: "确认移除" }).click();
  await expect.poll(() => deleted).toBe(true);
  await expect(page.getByText("购物车还是空的。")).toBeVisible();
});

test("Cart clear confirms, sends DELETE /api/cart and renders empty state", async ({ page }) => {
  let clearRequested = false;
  await openManagedCart(page, cartFixture(), { get: () => clearRequested ? { items: [], item_count: 0, total_quantity: 0, subtotal: null, currency: null, warnings: [] } : cartFixture(), delete: async (route) => { clearRequested = route.request().url().endsWith("/api/cart"); await route.fulfill({ status: 204 }); } });
  await page.getByRole("button", { name: "清空购物车" }).click();
  await expect(page.getByRole("dialog", { name: "清空购物车" })).toContainText("确定清空 ShopMind 购物车吗？");
  await page.getByRole("button", { name: "确认清空" }).click();
  await expect.poll(() => clearRequested).toBe(true);
  await expect(page.getByText("购物车还是空的。")).toBeVisible();
});

test("inactive Cart item stays visible, quantity is disabled and delete remains enabled", async ({ page }) => {
  const inactive = cartItemFixture({ effective_sale_status: "inactive", product_sale_status: "inactive", availability: { sale_status: "inactive", in_stock: false, available_quantity: 0, reason_code: "out_of_stock" } });
  await openManagedCart(page, cartFixture(inactive));
  await expect(page.getByRole("textbox", { name: "E2E 商品 数量" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "删除" })).toBeEnabled();
});

test("Phase 2 PendingAction confirmation exposes the Cart, then permits quantity editing", async ({ page }) => {
  let patchBody: Record<string, unknown> | null = null;
  let current = cartFixture();
  const updated = cartItemFixture({ quantity: 2, version: 2, subtotal_money: { amount: "11998.00", currency: "CNY" } });
  await openManagedCart(page, current, { get: () => current, patch: async (route) => { patchBody = JSON.parse(route.request().postData() ?? "{}"); current = cartFixture(updated); await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ item: updated, cart: current }) }); } });
  await expect(page.locator(".shopmind-cart-panel").getByRole("heading", { name: "E2E 商品" })).toBeVisible();
  await page.getByRole("textbox", { name: "E2E 商品 数量" }).fill("2");
  await page.getByRole("button", { name: "更新" }).click();
  await expect.poll(() => patchBody).toEqual({ expected_version: 1, quantity: 2 });
});
