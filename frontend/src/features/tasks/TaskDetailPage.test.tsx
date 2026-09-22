import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SessionProvider } from "../../app/session";
import type { ShoppingTaskSnapshot } from "./taskTypes";
import { TaskDetailPage } from "./TaskDetailPage";

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** An SSE response with no frames: `parseSseText` yields `[]`, so the events effect no-ops
 *  instead of invalidating the query, and retries no sooner than 750ms — well past any of
 *  these tests' lifetime. */
function emptyEventStream() {
  return new Response("", { status: 200, headers: { "Content-Type": "text/event-stream" } });
}

function baseSnapshot(overrides: Partial<ShoppingTaskSnapshot> = {}): ShoppingTaskSnapshot {
  return {
    task_id: "task-1",
    owner_id: "demo-user",
    kind: "bundle_selection",
    status: "succeeded",
    mode: "offline",
    version: 3,
    goal: {
      kind: "bundle_selection",
      goal_text: "为办公场景选一套笔记本、显示器和扩展坞",
      required_slots: [],
      open_questions: [],
      hard_constraints: {},
      soft_requirements: {},
    },
    plan: {
      steps: [
        {
          key: "search",
          capability: "product_search",
          role: "product",
          depends_on: [],
          output_kind: "candidates",
        },
        {
          key: "compose",
          capability: "bundle_compose",
          role: "decision",
          depends_on: ["search"],
          output_kind: "bundle",
        },
      ],
    },
    steps: [
      {
        key: "search",
        capability: "product_search",
        role: "product",
        status: "succeeded",
        attempt_count: 1,
        output_artifact_id: "artifact-1",
      },
      {
        key: "compose",
        capability: "bundle_compose",
        role: "decision",
        status: "succeeded",
        attempt_count: 1,
        output_artifact_id: "artifact-2",
      },
    ],
    artifacts: [
      {
        id: "artifact-2",
        kind: "bundle_proposal",
        branch: "compose",
        status: "verified",
        payload: {},
      },
    ],
    output: null,
    pending_interaction: null,
    last_sequence: 4,
    ...overrides,
  };
}

function renderTaskDetail(taskId = "task-1") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SessionProvider>
        <MemoryRouter initialEntries={[`/tasks/${taskId}`]}>
          <Routes>
            <Route element={<TaskDetailPage />} path="/tasks/:taskId" />
            <Route element={<div data-testid="tasks-list-stub">on tasks list</div>} path="/tasks" />
          </Routes>
        </MemoryRouter>
      </SessionProvider>
    </QueryClientProvider>,
  );
}

describe("Durable task workbench: task detail", () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.restoreAllMocks();
  });

  it("renders plan steps and artifacts from the snapshot", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(baseSnapshot())));
    renderTaskDetail();
    expect(await screen.findByRole("heading", { name: /为办公场景选一套/ })).toBeInTheDocument();
    expect(screen.getByText("2 步")).toBeInTheDocument();
    expect(screen.getByText("search")).toBeInTheDocument();
    expect(screen.getByText("compose")).toBeInTheDocument();
    expect(screen.getByText("product · product_search")).toBeInTheDocument();
    expect(screen.getByText("decision · bundle_compose")).toBeInTheDocument();
    expect(screen.getByText("1 份产物")).toBeInTheDocument();
    expect(screen.getByText("bundle_proposal")).toBeInTheDocument();
    expect(screen.getByText("compose · verified")).toBeInTheDocument();
  });

  it("shows the not-found state when the snapshot can't be read", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse({ code: "not_found", message: "not found" }, 404)),
    );
    renderTaskDetail();
    expect(await screen.findByRole("alert")).toHaveTextContent("任务不存在或当前 owner 无权读取。");
    fireEvent.click(screen.getByRole("link", { name: "返回任务列表" }));
    expect(await screen.findByTestId("tasks-list-stub")).toBeInTheDocument();
  });

  it("cancels a non-terminal task with the current version and disables the button afterward", async () => {
    let cancelled = false;
    const fetchMock = vi
      .fn()
      .mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.includes("/events")) return emptyEventStream();
        if (url.endsWith("/cancel") && init?.method === "POST") {
          cancelled = true;
          return jsonResponse({ task_id: "task-1", status: "cancelled", version: 4 });
        }
        return jsonResponse(
          baseSnapshot(
            cancelled ? { status: "cancelled", version: 4 } : { status: "waiting_input" },
          ),
        );
      });
    vi.stubGlobal("fetch", fetchMock);
    renderTaskDetail();
    const cancelButton = await screen.findByRole("button", { name: "取消任务" });
    expect(cancelButton).toBeEnabled();
    fireEvent.click(cancelButton);
    await waitFor(() => expect(screen.getByRole("button", { name: "取消任务" })).toBeDisabled());
    const cancelCall = fetchMock.mock.calls.find(
      ([reqInput, reqInit]) => String(reqInput).endsWith("/cancel") && reqInit?.method === "POST",
    );
    expect(cancelCall).toBeDefined();
    const body = JSON.parse(String(cancelCall?.[1]?.body)) as Record<string, unknown>;
    expect(body).toMatchObject({ user_id: "demo-user", expected_version: 3 });
  });

  it("submits supplementary feedback as a user-reported observation and clears the field", async () => {
    let submitted = false;
    const fetchMock = vi
      .fn()
      .mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.includes("/events")) return emptyEventStream();
        if (url.endsWith("/inputs") && init?.method === "POST") {
          submitted = true;
          return jsonResponse({ task_id: "task-1", status: "waiting_input", version: 4 });
        }
        return jsonResponse(baseSnapshot({ status: "waiting_input", version: submitted ? 4 : 3 }));
      });
    vi.stubGlobal("fetch", fetchMock);
    renderTaskDetail();
    const observationField = await screen.findByLabelText("用户补充事实");
    fireEvent.change(observationField, { target: { value: "实际到货的是灰色版本" } });
    fireEvent.click(screen.getByRole("button", { name: "提交补充" }));
    await waitFor(() => expect(screen.getByLabelText("用户补充事实")).toHaveValue(""));
    const inputsCall = fetchMock.mock.calls.find(
      ([reqInput, reqInit]) => String(reqInput).endsWith("/inputs") && reqInit?.method === "POST",
    );
    expect(inputsCall).toBeDefined();
    const body = JSON.parse(String(inputsCall?.[1]?.body)) as Record<string, unknown>;
    expect(body).toMatchObject({
      user_id: "demo-user",
      expected_version: 3,
      feedback: { observation: "实际到货的是灰色版本", source: "user_reported" },
    });
  });
});
