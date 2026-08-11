import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SessionProvider } from "../../app/session";
import { RunsPage } from "./RunsPage";

function renderRuns() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><SessionProvider><MemoryRouter><RunsPage /></MemoryRouter></SessionProvider></QueryClientProvider>);
}

describe("payload-free run inspector", () => {
  beforeEach(() => { window.localStorage.clear(); vi.restoreAllMocks(); });

  it("sends exactly one owner-bound run selector and hides event payloads", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      schema_version: "shopmind.owner-run-inspection.v1",
      run_id: "run-123",
      trace_id: "trace-123",
      thread_id: "thread-123",
      operation: "chat",
      mode: "multi",
      status: "completed",
      pending_action_id: null,
      usage: { input_tokens: 10, output_tokens: 5, total_tokens: 15, cost_usd: null, tool_call_count: 1, step_count: 2 },
      started_at: "2026-07-26T00:00:00Z",
      completed_at: "2026-07-26T00:00:01Z",
      client_event_count: 1,
      events: [{ sequence: 1, event_type: "run.started", agent_name: "supervisor", visibility: "client", created_at: "2026-07-26T00:00:00Z" }],
      event_limit: 50,
      events_truncated: false,
    }), { headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
    renderRuns();
    fireEvent.change(screen.getByTestId("run-selector"), { target: { value: "run-123" } });
    fireEvent.click(screen.getByTestId("run-inspect"));
    expect(await screen.findByText("run-123")).toBeInTheDocument();
    expect(screen.getByText("run.started")).toBeInTheDocument();
    expect(screen.queryByText(/payload-value/)).not.toBeInTheDocument();
    const request = JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body)) as Record<string, unknown>;
    expect(request).toMatchObject({ user_id: "demo-user", run_id: "run-123", event_limit: 50 });
    expect(request.trace_id).toBeUndefined();
  });
});
