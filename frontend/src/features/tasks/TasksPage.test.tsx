import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SessionProvider } from "../../app/session";
import { TasksPage } from "./TasksPage";

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function emptyList() {
  return jsonResponse({ items: [], limit: 20, offset: 0 });
}

function renderTasks() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SessionProvider>
        <MemoryRouter initialEntries={["/tasks"]}>
          <Routes>
            <Route element={<TasksPage />} path="/tasks" />
            <Route
              element={<div data-testid="task-detail-stub">on task detail</div>}
              path="/tasks/:taskId"
            />
          </Routes>
        </MemoryRouter>
      </SessionProvider>
    </QueryClientProvider>,
  );
}

describe("Durable task workbench: list and create form", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("lists existing tasks with kind label, id prefix, status and mode", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({
          items: [
            {
              task_id: "11111111-2222-3333-4444-555555555555",
              kind: "bundle_selection",
              status: "running",
              mode: "agent",
              version: 1,
              created_at: "2026-09-01T00:00:00Z",
            },
            {
              task_id: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
              kind: "compatibility_diagnosis",
              status: "succeeded",
              mode: "offline",
              version: 2,
              created_at: "2026-09-02T00:00:00Z",
            },
          ],
          limit: 20,
          offset: 0,
        }),
      ),
    );
    renderTasks();
    expect(await screen.findByText("2 项")).toBeInTheDocument();
    // Query by row (task-id prefix, which is unique) rather than by kind label alone: the
    // kind labels ("组合选购" etc.) also appear as <option> text in the create form's select.
    const firstRow = screen.getByRole("link", { name: /11111111/ });
    expect(firstRow).toHaveTextContent("组合选购");
    expect(firstRow).toHaveTextContent("running");
    expect(firstRow).toHaveTextContent("agent");
    const secondRow = screen.getByRole("link", { name: /aaaaaaaa/ });
    expect(secondRow).toHaveTextContent("兼容排查");
    expect(secondRow).toHaveTextContent("succeeded");
    expect(secondRow).toHaveTextContent("offline");
  });

  it("shows the empty state when there are no tasks", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(emptyList()));
    renderTasks();
    expect(await screen.findByText("还没有任务。先创建一个离线任务开始演示。")).toBeInTheDocument();
  });

  it("disables the create button once the goal text is cleared", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(emptyList()));
    renderTasks();
    await screen.findByText("还没有任务。先创建一个离线任务开始演示。");
    fireEvent.change(screen.getByLabelText("目标"), { target: { value: "   " } });
    expect(screen.getByRole("button", { name: "创建任务" })).toBeDisabled();
  });

  it("creates a task with the selected kind and goal text, then navigates to its detail page", async () => {
    const fetchMock = vi
      .fn()
      .mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url === "/api/shopping-tasks" && method === "POST") {
          return jsonResponse(
            { task_id: "new-task-id", status: "queued", version: 1, mode: "offline" },
            202,
          );
        }
        return emptyList();
      });
    vi.stubGlobal("fetch", fetchMock);
    renderTasks();
    await screen.findByText("还没有任务。先创建一个离线任务开始演示。");
    fireEvent.change(screen.getByLabelText("任务类型"), {
      target: { value: "compatibility_diagnosis" },
    });
    fireEvent.click(screen.getByRole("button", { name: "创建任务" }));
    expect(await screen.findByTestId("task-detail-stub")).toBeInTheDocument();
    const postCall = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(postCall).toBeDefined();
    const body = JSON.parse(String(postCall?.[1]?.body)) as Record<string, unknown>;
    expect(body).toMatchObject({
      user_id: "demo-user",
      kind: "compatibility_diagnosis",
      goal_text: "我想为办公场景选择笔记本、显示器和扩展坞",
    });
  });
});
