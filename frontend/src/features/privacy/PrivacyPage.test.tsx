import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SessionProvider } from "../../app/session";
import { PrivacyPage } from "./PrivacyPage";

function renderPrivacy() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}><SessionProvider><MemoryRouter><PrivacyPage /></MemoryRouter></SessionProvider></QueryClientProvider>);
}

const snapshot = {
  counts: { preferences: 1, cart_items: 0, pending_actions: 0, candidate_contexts: 0, conversation_threads: 1, conversation_messages: 2, agent_runs: 1, agent_run_events: 2, conversation_summaries: 0, idempotency_records: 0, memory_records: 1 },
  total_records: 7,
  memories: [{ memory_id: "memory-1", thread_id: "thread-1", kind: "working", scope: "user", content: "prefers quiet products", content_json: {}, priority: 1, token_count: 3, confidence: 0.9, status: "active", expires_at: null, deleted_at: null, created_at: "2026-07-26T00:00:00Z", updated_at: "2026-07-26T00:00:00Z" }],
  memory_limit: 50,
  memory_truncated: false,
};

describe("Privacy Center", () => {
  beforeEach(() => { window.localStorage.clear(); vi.restoreAllMocks(); });

  it("loads the exact-owner inventory and corrects a Memory", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(snapshot));
    vi.stubGlobal("fetch", fetchMock);
    renderPrivacy();
    expect(await screen.findByText("7 条记录")).toBeInTheDocument();
    expect(screen.getByTestId("memory-content-memory-1")).toHaveValue("prefers quiet products");
    fireEvent.change(screen.getByTestId("memory-content-memory-1"), { target: { value: "prefers silent products" } });
    fireEvent.click(screen.getByTestId("memory-correct-memory-1"));
    await waitFor(() => expect(fetchMock.mock.calls.some(([url]) => url === "/api/owner-data/memory/correct")).toBe(true));
    const correctionCall = fetchMock.mock.calls.find(([url]) => url === "/api/owner-data/memory/correct");
    expect(JSON.parse(String(correctionCall?.[1]?.body))).toMatchObject({ user_id: "demo-user", memory_id: "memory-1", content: "prefers silent products" });
  });

  it("requires the exact phrase before full owner-data deletion", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(snapshot));
    vi.stubGlobal("fetch", fetchMock);
    renderPrivacy();
    await screen.findByText("7 条记录");
    expect(screen.getByTestId("delete-owner-button")).toBeDisabled();
    fireEvent.change(screen.getByTestId("delete-owner-data"), { target: { value: "删除我的全部 ShopMind 数据" } });
    expect(screen.getByTestId("delete-owner-button")).toBeEnabled();
  });
});

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}
