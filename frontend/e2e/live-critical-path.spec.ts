import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
import { expect, test } from "@playwright/test";

const repositoryRoot = resolve(process.cwd(), "..");
const verifierPython = process.env.SHOPMIND_PYTHON ?? "python";
const backendUrl = process.env.SHOPMIND_BACKEND_URL ?? "http://127.0.0.1:8000";
const frontendUrl = process.env.SHOPMIND_FRONTEND_URL ?? "http://127.0.0.1:5173";
const demoEnvironment = {
  ...process.env,
  SHOPMIND_DEPLOYMENT_PROFILE: "offline-demo",
  LANGSMITH_TRACING: "false",
  LANGCHAIN_TRACING_V2: "false",
  LANGSMITH_API_KEY: "",
  SHOPMIND_OUTBOX_ENABLED: "false",
};

function runDemoSmoke(args: string[]): Record<string, unknown> {
  const output = execFileSync(
    verifierPython,
    ["scripts/smoke_shopmind_demo.py", "--backend-url", backendUrl, "--frontend-url", frontendUrl, ...args, "--json"],
    { cwd: repositoryRoot, env: demoEnvironment, encoding: "utf8" },
  ).trim();
  const jsonLine = output.split(/\r?\n/).reverse().find((line) => line.trim().startsWith("{"));
  if (!jsonLine) throw new Error(`Smoke verifier did not return JSON: ${output}`);
  return JSON.parse(jsonLine) as Record<string, unknown>;
}

test("real core path reaches paid Order and exact PostgreSQL facts", async ({ page }) => {
  const userId = `live-demo-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  const snapshot = runDemoSmoke(["--snapshot-inventory"]);

  await page.goto("/");
  const identityInput = page.getByLabel("开发用户标识");
  await identityInput.fill(userId);
  await expect(identityInput).toHaveValue(userId);

  await page.getByTestId("json-mode-button").click();
  await page.getByTestId("chat-input").fill("laptop，预算 12000 元以内，主要用于 Java 开发，内存至少 16GB，希望尽量轻");
  await page.getByTestId("send-button").click();

  const recommendation = page.locator("article.recommendation-card").first();
  await expect(recommendation).toBeVisible();
  await recommendation.getByRole("button", { name: "选择此商品" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByTestId("action-confirm").click();

  await expect(page.getByRole("button", { name: "去结算" })).toBeVisible();
  await page.getByRole("button", { name: "去结算" }).click();
  await expect(page.getByTestId("checkout-preview")).toBeVisible();
  await page.getByRole("button", { name: "Confirm order" }).click();

  await expect(page).toHaveURL(/\/orders\/[0-9a-f-]+$/);
  await expect(page.getByTestId("order-confirmation")).toBeVisible();
  await page.getByRole("button", { name: "Mock Payment" }).click();
  await expect(page.getByTestId("payment-paid")).toBeVisible();
  await expect(page.getByTestId("order-detail")).toContainText("paid");

  const orderId = new URL(page.url()).pathname.split("/").pop();
  expect(orderId).toBeTruthy();
  const facts = runDemoSmoke([
    "--user-id",
    userId,
    "--order-id",
    orderId as string,
    "--require-paid",
    "--initial-inventory-json",
    JSON.stringify(snapshot.inventory),
  ]);
  expect(facts.status).toBe("pass");
  expect(facts.order_facts).toMatchObject({
    order_status: "paid",
    payment_attempts: ["succeeded"],
    outbox_event_types: ["shopmind.order.created.v1", "shopmind.payment.succeeded.v1"],
  });
});
