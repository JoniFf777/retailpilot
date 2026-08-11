import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { StatusPage } from "./StatusPage";

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><StatusPage /></QueryClientProvider>);
}

afterEach(() => vi.restoreAllMocks());

describe("StatusPage", () => {
  it("renders liveness and a blocked readiness report from the public endpoints", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/health/readiness")) {
        return new Response(JSON.stringify({ schema_version: "shopmind.deployment-readiness.v1", profile: "development", status: "blocked", ready: false, total_checks: 2, passed_checks: 1, failed_checks: 1, not_applicable_checks: 0, checks: [{ check_id: "postgres.connectivity", category: "database", status: "failed", reason: "postgres_unavailable" }, { check_id: "coordination.backend", category: "coordination", status: "passed", reason: "local_coordination_ready" }] }), { status: 503, headers: { "Content-Type": "application/json" } });
      }
      return new Response(JSON.stringify({ status: "ok" }), { status: 200, headers: { "Content-Type": "application/json" } });
    });

    renderPage();
    expect(await screen.findByText("服务存活")).toBeInTheDocument();
    expect(screen.getByText("blocked")).toBeInTheDocument();
    expect(screen.getByText("postgres.connectivity")).toBeInTheDocument();
  });
});
