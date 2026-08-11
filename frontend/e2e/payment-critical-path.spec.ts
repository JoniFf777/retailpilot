import { expect, test, type Page, type Route } from "@playwright/test";

type OrderStatus = "pending_payment" | "cancelled" | "paid";
type PaymentStatus = "processing" | "unknown" | "provider_succeeded" | "failed" | "succeeded";

function orderFixture(status: OrderStatus = "pending_payment") {
  return { order_id: "order-e2e-payment", status, currency: "CNY", subtotal: { amount: "5999.00", currency: "CNY" }, total: { amount: "5999.00", currency: "CNY" }, items: [{ item_id: "item-e2e-payment", sku_id: "sku-e2e-payment", product_code: "PAYMENT-1", product_name: "Payment Product", sku_code: "PAYMENT-SKU", sku_name: "Mock SKU", unit_money: { amount: "5999.00", currency: "CNY" }, quantity: 1, subtotal_money: { amount: "5999.00", currency: "CNY" } }], version: status === "paid" ? 2 : 1, created_at: "2026-08-08T00:00:00Z", updated_at: "2026-08-08T00:00:00Z" };
}

function paymentAttempt(status: PaymentStatus) {
  return { attempt_id: `attempt-${status}`, order_id: "order-e2e-payment", provider: "mock", status, amount: { amount: "5999.00", currency: "CNY" }, failure_code: status === "failed" || status === "unknown" ? "payment_declined" : null, provider_result_at: "2026-08-08T00:00:00Z", created_at: "2026-08-08T00:00:00Z", updated_at: "2026-08-08T00:00:00Z", completed_at: status === "failed" || status === "succeeded" ? "2026-08-08T00:00:00Z" : null };
}

function json(body: unknown, status = 200) {
  return { status, contentType: "application/json", body: JSON.stringify(body) };
}

type PaymentState = {
  order: ReturnType<typeof orderFixture>;
  attempts: ReturnType<typeof paymentAttempt>[];
  onPost?: (route: Route, keys: string[]) => Promise<void>;
};

async function installOrderApi(page: Page, state: PaymentState, keys: string[] = []) {
  await page.route("**/api/orders?*", async (route) => {
    if (route.request().method() === "GET") return route.fulfill(json({ items: [state.order], next_cursor: null }));
    return route.fallback();
  });
  await page.route("**/api/orders/order-e2e-payment?*", async (route) => {
    if (route.request().method() === "GET") return route.fulfill(json(state.order));
    return route.fallback();
  });
  await page.route("**/api/orders/order-e2e-payment/payments**", async (route) => {
    if (route.request().method() === "GET") {
      const isUserB = route.request().url().includes("user_id=user-b");
      return route.fulfill(json({ items: isUserB ? [] : state.attempts }));
    }
    const key = route.request().headers()["idempotency-key"] ?? "";
    keys.push(key);
    if (state.onPost) return state.onPost(route, keys);
    const succeeded = paymentAttempt("succeeded");
    state.attempts = [succeeded];
    state.order = orderFixture("paid");
    return route.fulfill(json({ payment_attempt: succeeded, order: state.order, idempotent_replay: false }));
  });
}

async function openOrder(page: Page, state: PaymentState, keys: string[] = []) {
  await installOrderApi(page, state, keys);
  await page.goto("/orders/order-e2e-payment");
  await expect(page.getByTestId("payment-section")).toBeVisible();
}

test("pending Order → Mock Payment → paid and paid persists after refresh", async ({ page }) => {
  const state: PaymentState = { order: orderFixture(), attempts: [] };
  const keys: string[] = [];
  await openOrder(page, state, keys);
  await page.getByRole("button", { name: "Mock Payment" }).click();
  await expect(page.getByTestId("payment-paid")).toBeVisible();
  expect(keys).toHaveLength(1);
  await page.reload();
  await expect(page.getByTestId("payment-paid")).toBeVisible();
  await expect(page.getByRole("button", { name: "Mock Payment" })).not.toBeVisible();
  await expect(page.getByRole("button", { name: "Cancel pending order" })).not.toBeVisible();
});

test("Checkout/Create Order → Payment completes the full frontend path", async ({ page }) => {
  const state: PaymentState = { order: orderFixture(), attempts: [] };
  await page.route("**/api/checkout/preview**", async (route) => await route.fulfill(json({ items: [{ cart_item_id: "cart-payment", sku_id: "sku-e2e-payment", product_name: "Payment Product", sku_name: "Mock SKU", quantity: 1, unit_money: { amount: "5999.00", currency: "CNY" }, subtotal_money: { amount: "5999.00", currency: "CNY" }, availability: { sale_status: "active", in_stock: true, available_quantity: 8 }, version: 1 }], item_count: 1, total_quantity: 1, subtotal: { amount: "5999.00", currency: "CNY" }, currency: "CNY", warnings: [], can_create_order: true, checkout_token: "payment-checkout-token", expires_at: "2026-08-08T00:10:00Z", revalidation_required: true })));
  await page.route("**/api/orders?*", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    return route.fulfill(json({ order: state.order, idempotent_replay: false }, 201));
  });
  await installOrderApi(page, state);
  await page.goto("/checkout");
  await page.getByRole("button", { name: "Confirm order" }).click();
  await expect(page.getByTestId("order-confirmation")).toBeVisible();
  await page.getByRole("button", { name: "Mock Payment" }).click();
  await expect(page.getByTestId("payment-paid")).toBeVisible();
});

test("double-click creates one PaymentAttempt", async ({ page }) => {
  const state: PaymentState = { order: orderFixture(), attempts: [] };
  const keys: string[] = [];
  await openOrder(page, state, keys);
  await page.getByRole("button", { name: "Mock Payment" }).dblclick();
  await expect(page.getByTestId("payment-paid")).toBeVisible();
  expect(keys).toHaveLength(1);
});

test("declined payment permits a new attempt with a new key", async ({ page }) => {
  const state: PaymentState = { order: orderFixture(), attempts: [] };
  const keys: string[] = [];
  state.onPost = async (route, seenKeys) => {
    if (seenKeys.length === 1) {
      const failed = paymentAttempt("failed");
      state.attempts = [failed];
      return route.fulfill(json({ code: "payment_declined", message: "declined", details: {}, idempotent_replay: false }, 402));
    }
    const succeeded = paymentAttempt("succeeded");
    state.attempts = [succeeded, paymentAttempt("failed")];
    state.order = orderFixture("paid");
    return route.fulfill(json({ payment_attempt: succeeded, order: state.order, idempotent_replay: false }));
  };
  await openOrder(page, state, keys);
  await page.getByRole("button", { name: "Mock Payment" }).click();
  await expect(page.getByRole("button", { name: "再次支付" })).toBeVisible();
  await page.getByRole("button", { name: "再次支付" }).click();
  await expect(page.getByTestId("payment-paid")).toBeVisible();
  expect(keys).toHaveLength(2);
  expect(keys[0]).not.toBe(keys[1]);
});

test("unknown payment reconciles with the same key", async ({ page }) => {
  const state: PaymentState = { order: orderFixture(), attempts: [] };
  const keys: string[] = [];
  state.onPost = async (route, seenKeys) => {
    if (seenKeys.length === 1) {
      state.attempts = [paymentAttempt("unknown")];
      return route.fulfill(json({ payment_attempt: paymentAttempt("unknown"), order: state.order, idempotent_replay: false }, 202));
    }
    const succeeded = paymentAttempt("succeeded");
    state.attempts = [succeeded];
    state.order = orderFixture("paid");
    return route.fulfill(json({ payment_attempt: succeeded, order: state.order, idempotent_replay: true }));
  };
  await openOrder(page, state, keys);
  await page.getByRole("button", { name: "Mock Payment" }).click();
  await expect(page.getByTestId("payment-status-unknown")).toBeVisible();
  await page.getByRole("button", { name: "继续查询" }).click();
  await expect(page.getByTestId("payment-paid")).toBeVisible();
  expect(keys[0]).toBe(keys[1]);
});

test("response lost retries the same key", async ({ page }) => {
  const state: PaymentState = { order: orderFixture(), attempts: [] };
  const keys: string[] = [];
  let posts = 0;
  state.onPost = async (route) => {
    posts += 1;
    if (posts === 1) return route.abort();
    const succeeded = paymentAttempt("succeeded");
    state.attempts = [succeeded];
    state.order = orderFixture("paid");
    return route.fulfill(json({ payment_attempt: succeeded, order: state.order, idempotent_replay: true }));
  };
  await openOrder(page, state, keys);
  await page.getByRole("button", { name: "Mock Payment" }).click();
  await expect(page.getByTestId("payment-status-unknown")).toBeVisible();
  await page.getByRole("button", { name: "继续查询" }).click();
  await expect(page.getByTestId("payment-paid")).toBeVisible();
  expect(keys[0]).toBe(keys[1]);
});

test("provider_succeeded/finalization pending only offers recovery, never a new payment", async ({ page }) => {
  const state: PaymentState = { order: orderFixture(), attempts: [] };
  const keys: string[] = [];
  state.onPost = async (route, seenKeys) => {
    if (seenKeys.length === 1) {
      state.attempts = [paymentAttempt("provider_succeeded")];
      return route.fulfill(json({ code: "payment_finalization_pending", message: "finalization pending", details: {}, idempotent_replay: true }, 503));
    }
    const succeeded = paymentAttempt("succeeded");
    state.attempts = [succeeded];
    state.order = orderFixture("paid");
    return route.fulfill(json({ payment_attempt: succeeded, order: state.order, idempotent_replay: true }));
  };
  await openOrder(page, state, keys);
  await page.getByRole("button", { name: "Mock Payment" }).click();
  await expect(page.getByTestId("payment-status-provider_succeeded")).toBeVisible();
  await expect(page.getByRole("button", { name: "Mock Payment" })).not.toBeVisible();
  await page.getByRole("button", { name: "继续完成" }).click();
  await expect(page.getByTestId("payment-paid")).toBeVisible();
  expect(keys[0]).toBe(keys[1]);
});

test("active Payment blocks Cancel with payment_in_progress UX", async ({ page }) => {
  const state: PaymentState = { order: orderFixture(), attempts: [paymentAttempt("processing")] };
  await openOrder(page, state);
  await expect(page.getByTestId("payment-in-progress")).toContainText("Cancel is unavailable");
  await expect(page.getByRole("button", { name: "Cancel pending order" })).not.toBeVisible();
});

test("identity switch does not expose or retry the previous user's Payment", async ({ page }) => {
  const state: PaymentState = { order: orderFixture(), attempts: [] };
  const keys: string[] = [];
  state.onPost = async (route) => {
    state.attempts = [paymentAttempt("unknown")];
    return route.fulfill(json({ payment_attempt: paymentAttempt("unknown"), order: state.order, idempotent_replay: false }, 202));
  };
  await openOrder(page, state, keys);
  await page.getByRole("button", { name: "Mock Payment" }).click();
  await expect(page.getByTestId("payment-status-unknown")).toBeVisible();
  await page.getByRole("link", { name: "Shopping", exact: true }).click();
  await expect(page.locator("#dev-user-id")).toBeVisible();
  await page.locator("#dev-user-id").fill("user-b");
  await expect(page.locator("#dev-user-id")).toHaveValue("user-b");
  await page.getByRole("link", { name: /^Orders/ }).click();
  await page.getByRole("link", { name: /order-e2e-payment/ }).click();
  await expect(page.getByRole("button", { name: "Mock Payment" })).toBeVisible();
  await expect(page.getByTestId("payment-status-unknown")).not.toBeVisible();
  expect(keys).toHaveLength(1);
});

test("identity A to B to A preserves the original Payment recovery key", async ({ page }) => {
  const state: PaymentState = { order: orderFixture(), attempts: [] };
  const keys: string[] = [];
  state.onPost = async (route, seenKeys) => {
    if (seenKeys.length === 1) {
      state.attempts = [paymentAttempt("unknown")];
      return route.fulfill(json({ payment_attempt: paymentAttempt("unknown"), order: state.order, idempotent_replay: false }, 202));
    }
    const succeeded = paymentAttempt("succeeded");
    state.attempts = [succeeded];
    state.order = orderFixture("paid");
    return route.fulfill(json({ payment_attempt: succeeded, order: state.order, idempotent_replay: true }));
  };
  await openOrder(page, state, keys);
  await page.getByRole("button", { name: "Mock Payment" }).click();
  await expect(page.getByTestId("payment-status-unknown")).toBeVisible();

  await page.getByRole("link", { name: "Shopping", exact: true }).click();
  await page.locator("#dev-user-id").fill("user-b");
  await page.getByRole("link", { name: /^Orders/ }).click();
  await page.getByRole("link", { name: /order-e2e-payment/ }).click();
  await expect(page.getByRole("button", { name: "Mock Payment" })).toBeVisible();
  await expect(page.getByTestId("payment-status-unknown")).not.toBeVisible();

  await page.getByRole("link", { name: "Shopping", exact: true }).click();
  await page.locator("#dev-user-id").fill("demo-user");
  await page.getByRole("link", { name: /^Orders/ }).click();
  await page.getByRole("link", { name: /order-e2e-payment/ }).click();
  await expect(page.getByTestId("payment-status-unknown")).toBeVisible();
  await page.getByTestId("payment-status-unknown").getByRole("button").click();
  await expect(page.getByTestId("payment-paid")).toBeVisible();
  expect(keys).toHaveLength(2);
  expect(keys[0]).toBe(keys[1]);
});

test("payment_in_progress discards the rejected local attempt and allows a new attempt after failure", async ({ page }) => {
  const state: PaymentState = { order: orderFixture(), attempts: [] };
  const keys: string[] = [];
  state.onPost = async (route, seenKeys) => {
    if (seenKeys.length === 1) {
      state.attempts = [paymentAttempt("processing")];
      return route.fulfill(json({ code: "payment_in_progress", message: "Payment is already in progress", details: {}, idempotent_replay: false }, 409));
    }
    const succeeded = paymentAttempt("succeeded");
    state.attempts = [succeeded, paymentAttempt("failed")];
    state.order = orderFixture("paid");
    return route.fulfill(json({ payment_attempt: succeeded, order: state.order, idempotent_replay: false }));
  };
  await openOrder(page, state, keys);
  await page.getByRole("button", { name: "Mock Payment" }).click();
  await expect(page.getByTestId("payment-in-progress")).toBeVisible();

  state.attempts = [paymentAttempt("failed")];
  await page.reload();
  await expect(page.getByRole("button", { name: "Mock Payment" })).toBeVisible();
  await page.getByRole("button", { name: "Mock Payment" }).click();
  await expect(page.getByTestId("payment-paid")).toBeVisible();
  expect(keys).toHaveLength(2);
  expect(keys[0]).not.toBe(keys[1]);
});

test("idempotency conflict does not auto-retry and requires an explicit new Payment", async ({ page }) => {
  const state: PaymentState = { order: orderFixture(), attempts: [] };
  const keys: string[] = [];
  state.onPost = async (route, seenKeys) => {
    if (seenKeys.length === 1) return route.fulfill(json({ code: "idempotency_conflict", message: "conflict", details: {}, idempotent_replay: false }, 409));
    const succeeded = paymentAttempt("succeeded");
    state.attempts = [succeeded];
    state.order = orderFixture("paid");
    return route.fulfill(json({ payment_attempt: succeeded, order: state.order, idempotent_replay: false }));
  };
  await openOrder(page, state, keys);
  await page.getByRole("button", { name: "Mock Payment" }).click();
  await expect(page.getByTestId("payment-idempotency-conflict")).toContainText("Automatic retry stopped");
  expect(keys).toHaveLength(1);
  await page.getByRole("button", { name: "Mock Payment" }).click();
  await expect(page.getByTestId("payment-paid")).toBeVisible();
  expect(keys).toHaveLength(2);
  expect(keys[0]).not.toBe(keys[1]);
});
