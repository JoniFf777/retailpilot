import { expect, test, type APIRequestContext } from "@playwright/test";

type CreatedTask = { task_id: string; status: string; version: number };
type TaskSnapshot = {
  status: string;
  version: number;
  last_sequence: number;
  steps: Array<{ status: string }>;
  plan?: { revision?: number };
  output?: { outcome?: string; bundle_proposal?: { options?: unknown[] } };
};

async function createTask(
  request: APIRequestContext,
  kind: string,
  goal: string,
  userId: string,
  known_facts: unknown[] = [],
): Promise<CreatedTask> {
  const response = await request.post("/api/shopping-tasks", {
    headers: { "Idempotency-Key": `browser-${kind}-${Date.now()}-${Math.random()}` },
    data: { user_id: userId, kind, goal_text: goal, known_facts },
  });
  expect(response.status()).toBe(202);
  return (await response.json()) as CreatedTask;
}

async function waitForTerminal(
  request: APIRequestContext,
  taskId: string,
  userId: string,
): Promise<TaskSnapshot> {
  let latest: unknown;
  for (let attempt = 0; attempt < 40; attempt += 1) {
    const response = await request.get(
      `/api/shopping-tasks/${taskId}?user_id=${encodeURIComponent(userId)}`,
    );
    if (response.status() !== 200)
      throw new Error(`task snapshot failed: ${response.status()} ${await response.text()}`);
    const snapshot = (await response.json()) as TaskSnapshot;
    latest = snapshot;
    if (["succeeded", "failed", "cancelled", "expired"].includes(snapshot.status)) return snapshot;
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`task ${taskId} did not reach a terminal state: ${JSON.stringify(latest)}`);
}

async function waitForStatus(
  request: APIRequestContext,
  taskId: string,
  userId: string,
  status: string,
) {
  for (let attempt = 0; attempt < 40; attempt += 1) {
    const response = await request.get(
      `/api/shopping-tasks/${taskId}?user_id=${encodeURIComponent(userId)}`,
    );
    expect(response.status()).toBe(200);
    const snapshot = (await response.json()) as { status: string };
    if (snapshot.status === status) return snapshot;
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`task ${taskId} did not reach ${status}`);
}

test("task workbench creates and renders a real bundle task", async ({ page }) => {
  await page.goto("/tasks");
  await expect(page.getByRole("heading", { name: "任务工作台" })).toBeVisible();
  await page.getByLabel("目标").fill("预算 12000 元，选择笔记本、显示器和扩展坞");
  await page.getByRole("button", { name: "创建任务" }).click();
  await expect(page).toHaveURL(/\/tasks\/[0-9a-f-]+/);
  await expect(page.getByRole("heading", { name: /预算 12000/ })).toBeVisible();
  await expect(page.getByText(/计划与步骤/)).toBeVisible();
});

test("real API and worker complete diagnosis and after-sales task snapshots", async ({
  page,
  request,
}) => {
  const userId = "demo-user";
  for (const [kind, goal] of [
    ["compatibility_diagnosis", "扩展坞连接后没有画面"],
    ["after_sales_assessment", "分析我的订单售后资格"],
  ] as const) {
    const facts =
      kind === "compatibility_diagnosis"
        ? [
            {
              key: "device",
              value: "扩展坞",
              source_ref: { source: "user_reported", source_id: "browser-device", verified: false },
            },
            {
              key: "symptom",
              value: "没有画面",
              source_ref: {
                source: "user_reported",
                source_id: "browser-symptom",
                verified: false,
              },
            },
          ]
        : [
            {
              key: "order_id",
              value: "missing-order-for-demo",
              source_ref: { source: "user_reported", source_id: "browser-order", verified: false },
            },
          ];
    const created = await createTask(request, kind, goal, userId, facts);
    const snapshot = (await waitForTerminal(request, created.task_id, userId)) as {
      status: string;
      version: number;
      steps: Array<{ status: string }>;
    };
    expect(snapshot.steps.length).toBeGreaterThan(0);
    await page.goto(`/tasks/${created.task_id}`);
    await expect(page.getByText(goal)).toBeVisible();
    if (kind === "after_sales_assessment") {
      const preview = await request.post(`/api/shopping-tasks/${created.task_id}/actions`, {
        headers: { "Idempotency-Key": `browser-draft-preview-${Date.now()}` },
        data: {
          user_id: userId,
          expected_version: snapshot.version,
          action_type: "save_after_sales_draft",
        },
      });
      expect(preview.status()).toBe(200);
      const previewBody = (await preview.json()) as { action_id: string; version: number };
      const confirmKey = `browser-draft-confirm-${Date.now()}`;
      const confirmed = await request.post(
        `/api/shopping-tasks/${created.task_id}/actions/${previewBody.action_id}/confirm`,
        {
          headers: { "Idempotency-Key": confirmKey },
          data: { user_id: userId, expected_version: previewBody.version, confirmed: true },
        },
      );
      expect(confirmed.status()).toBe(200);
      expect((await confirmed.json()).draft_only).toBe(true);
      const replay = await request.post(
        `/api/shopping-tasks/${created.task_id}/actions/${previewBody.action_id}/confirm`,
        {
          headers: { "Idempotency-Key": confirmKey },
          data: { user_id: userId, expected_version: previewBody.version, confirmed: true },
        },
      );
      expect(replay.status()).toBe(200);
    }
  }

  const actionUser = `action-user-${Date.now()}`;
  const bundle = await createTask(
    request,
    "bundle_selection",
    "预算 12000 元的办公三件套",
    actionUser,
    [
      {
        key: "budget",
        value: 12000,
        source_ref: { source: "user_reported", source_id: "browser-budget", verified: false },
      },
      {
        key: "currency",
        value: "CNY",
        source_ref: { source: "user_reported", source_id: "browser-currency", verified: false },
      },
    ],
  );
  const bundleSnapshot = await waitForTerminal(request, bundle.task_id, actionUser);
  expect(bundleSnapshot.status).toBe("succeeded");
  expect(bundleSnapshot.output?.outcome).toBe("recommended");
  const preview = await request.post(`/api/shopping-tasks/${bundle.task_id}/actions`, {
    headers: { "Idempotency-Key": `browser-action-${Date.now()}` },
    data: {
      user_id: actionUser,
      expected_version: bundleSnapshot.version,
      action_type: "add_bundle_to_cart",
    },
  });
  expect(preview.status()).toBe(200);
  const previewBody = (await preview.json()) as { action_id: string; version: number };
  const confirmed = await request.post(
    `/api/shopping-tasks/${bundle.task_id}/actions/${previewBody.action_id}/confirm`,
    {
      headers: { "Idempotency-Key": `browser-confirm-${Date.now()}` },
      data: { user_id: actionUser, expected_version: previewBody.version, confirmed: true },
    },
  );
  expect(confirmed.status()).toBe(200);
  const cart = await request.get(`/api/cart?user_id=${encodeURIComponent(actionUser)}`);
  expect(cart.status()).toBe(200);
  expect((await cart.json()).items.length).toBeGreaterThanOrEqual(3);
});

test("browser reconnects from a cursor and continues waiting input as a new plan revision", async ({
  request,
}) => {
  const userId = `resume-user-${Date.now()}`;
  const created = await createTask(
    request,
    "bundle_selection",
    "选择笔记本、显示器和扩展坞",
    userId,
  );
  await waitForStatus(request, created.task_id, userId, "waiting_input");
  const before = await request.get(
    `/api/shopping-tasks/${created.task_id}?user_id=${encodeURIComponent(userId)}`,
  );
  const beforeSnapshot = (await before.json()) as { version: number; last_sequence: number };
  const initialEvents = await request.get(
    `/api/shopping-tasks/${created.task_id}/events?user_id=${encodeURIComponent(userId)}&after_sequence=0`,
  );
  expect(initialEvents.status()).toBe(200);
  const continued = await request.post(`/api/shopping-tasks/${created.task_id}/inputs`, {
    headers: { "Idempotency-Key": `browser-inputs-${Date.now()}` },
    data: {
      user_id: userId,
      expected_version: beforeSnapshot.version,
      facts: [
        {
          key: "budget",
          value: 12000,
          source_ref: {
            source: "user_reported",
            source_id: "browser-resume-budget",
            verified: false,
          },
        },
        {
          key: "currency",
          value: "CNY",
          source_ref: {
            source: "user_reported",
            source_id: "browser-resume-currency",
            verified: false,
          },
        },
      ],
    },
  });
  expect(continued.status()).toBe(200);
  const finalSnapshot = await waitForTerminal(request, created.task_id, userId);
  expect(finalSnapshot.plan?.revision).toBe(2);
  const reconnect = await request.get(
    `/api/shopping-tasks/${created.task_id}/events?user_id=${encodeURIComponent(userId)}&after_sequence=${beforeSnapshot.last_sequence}`,
  );
  expect(reconnect.status()).toBe(200);
  expect(await reconnect.text()).toContain("task.inputs_received");
});
