import { QueryClient, QueryClientProvider, type UseQueryResult } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SessionProvider } from "../../app/session";
import { useSession } from "../../app/useSession";
import type { OrderView, PaymentAttemptListResponse } from "../../api/contracts";
import { clearAllPaymentSubmissions, newPaymentSubmission, readPaymentSubmission, updatePaymentSubmission } from "./paymentAttempt";
import { PaymentSection } from "./PaymentSection";

function order(status: OrderView["status"] = "pending_payment"): OrderView {
  return { order_id: "order-1", status, currency: "CNY", subtotal: { amount: "5999.00", currency: "CNY" }, total: { amount: "5999.00", currency: "CNY" }, items: [], version: 1, created_at: "2026-08-08T00:00:00Z", updated_at: "2026-08-08T00:00:00Z" };
}

function attempt(status: "processing" | "unknown" | "provider_succeeded" | "failed" | "succeeded" = "unknown") {
  return { attempt_id: `attempt-${status}`, order_id: "order-1", provider: "mock" as const, status, amount: { amount: "5999.00", currency: "CNY" }, failure_code: status === "failed" || status === "unknown" ? "payment_declined" : null, provider_result_at: "2026-08-08T00:00:00Z", created_at: "2026-08-08T00:00:00Z", updated_at: "2026-08-08T00:00:00Z", completed_at: status === "failed" || status === "succeeded" ? "2026-08-08T00:00:00Z" : null };
}

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function paymentQuery(items: ReturnType<typeof attempt>[] = []): UseQueryResult<PaymentAttemptListResponse, Error> {
  return { data: { items }, error: null, isError: false, isLoading: false, isPending: false, refetch: vi.fn() } as unknown as UseQueryResult<PaymentAttemptListResponse, Error>;
}

function renderSection(fetchMock: ReturnType<typeof vi.fn>, currentOrder = order(), query = paymentQuery()) {
  vi.stubGlobal("fetch", fetchMock);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}><SessionProvider><PaymentSection backendUserId="demo-user" identity="demo-user" order={currentOrder} paymentQuery={query} /></SessionProvider></QueryClientProvider>);
}

function renderSectionWithClient(fetchMock: ReturnType<typeof vi.fn>, currentOrder = order(), query = paymentQuery()) {
  vi.stubGlobal("fetch", fetchMock);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(<QueryClientProvider client={client}><SessionProvider><PaymentSection backendUserId="demo-user" identity="demo-user" order={currentOrder} paymentQuery={query} /></SessionProvider></QueryClientProvider>);
  return client;
}

function paymentResponse(status: "processing" | "unknown" | "provider_succeeded" | "failed" | "succeeded", orderStatus: OrderView["status"] = "pending_payment") {
  return { payment_attempt: attempt(status), order: order(orderStatus), idempotent_replay: false };
}

describe("Mock Payment recovery UX", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    clearAllPaymentSubmissions();
  });

  it("creates one key, then retries an unknown result with the same key and body", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(paymentResponse("unknown"), 202))
      .mockResolvedValueOnce(jsonResponse(paymentResponse("succeeded", "paid")));
    renderSection(fetchMock);

    fireEvent.click(screen.getByRole("button", { name: "Mock Payment" }));
    expect(await screen.findByTestId("payment-status-unknown")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "继续查询" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));

    const first = fetchMock.mock.calls[0]?.[1] as RequestInit;
    const second = fetchMock.mock.calls[1]?.[1] as RequestInit;
    expect(new Headers(first.headers).get("Idempotency-Key")).toBe(new Headers(second.headers).get("Idempotency-Key"));
    expect(first.body).toBe(second.body);
    expect(readPaymentSubmission("demo-user", "order-1")).toBeNull();
  });

  it("keeps provider_unavailable distinct from backend Attempt unknown and retries the original request", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ code: "payment_provider_unavailable", message: "temporarily unavailable", details: {}, idempotent_replay: false }, 503))
      .mockResolvedValueOnce(jsonResponse(paymentResponse("succeeded", "paid")));
    renderSection(fetchMock);

    fireEvent.click(screen.getByRole("button", { name: "Mock Payment" }));
    expect(await screen.findByTestId("payment-provider-unavailable")).toBeInTheDocument();
    expect(screen.queryByTestId("payment-status-unknown")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry original request" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));

    const keys = fetchMock.mock.calls.map((call) => new Headers((call[1] as RequestInit).headers).get("Idempotency-Key"));
    expect(keys[0]).toBe(keys[1]);
  });

  it("uses the same key for provider_succeeded finalization recovery", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ code: "payment_finalization_pending", message: "finalization pending", details: {}, idempotent_replay: true }, 503))
      .mockResolvedValueOnce(jsonResponse(paymentResponse("succeeded", "paid")));
    renderSection(fetchMock);

    fireEvent.click(screen.getByRole("button", { name: "Mock Payment" }));
    expect(await screen.findByTestId("payment-status-provider_succeeded")).toHaveTextContent("不能重新支付");
    fireEvent.click(screen.getByRole("button", { name: "继续完成" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(new Headers(fetchMock.mock.calls[0]?.[1]?.headers).get("Idempotency-Key")).toBe(new Headers(fetchMock.mock.calls[1]?.[1]?.headers).get("Idempotency-Key"));
  });

  it("allows a new key only after a declined attempt", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ code: "payment_declined", message: "declined", details: {}, idempotent_replay: false }, 402))
      .mockResolvedValueOnce(jsonResponse(paymentResponse("succeeded", "paid")));
    renderSection(fetchMock);

    fireEvent.click(screen.getByRole("button", { name: "Mock Payment" }));
    expect(await screen.findByText("Payment failed. Start a new Mock Payment attempt when you are ready.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "再次支付" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(new Headers(fetchMock.mock.calls[0]?.[1]?.headers).get("Idempotency-Key")).not.toBe(new Headers(fetchMock.mock.calls[1]?.[1]?.headers).get("Idempotency-Key"));
  });

  it("blocks a second payment while an active Payment Attempt exists and renders paid correctly", () => {
    const fetchMock = vi.fn();
    renderSection(fetchMock, order("pending_payment"), paymentQuery([attempt("processing")]));
    expect(screen.getByTestId("payment-in-progress")).toHaveTextContent("Cancel is unavailable");
    expect(screen.queryByRole("button", { name: "Mock Payment" })).not.toBeInTheDocument();

    cleanup();
    renderSection(fetchMock, order("paid"), paymentQuery([attempt("succeeded")]));
    expect(screen.getByTestId("payment-paid")).toHaveTextContent("支付成功");
    expect(screen.queryByRole("button", { name: "Mock Payment" })).not.toBeInTheDocument();
  });

  it("invalidates Order detail, Orders list, and Payment history on success but never Cart", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(paymentResponse("succeeded", "paid")));
    const client = renderSectionWithClient(fetchMock);
    const invalidate = vi.spyOn(client, "invalidateQueries");
    fireEvent.click(screen.getByRole("button", { name: "Mock Payment" }));
    await waitFor(() => expect(invalidate).toHaveBeenCalled());
    const keys = invalidate.mock.calls.map(([filters]) => filters?.queryKey);
    expect(keys).toContainEqual(["shopmind-order", "demo-user", "order-1"]);
    expect(keys).toContainEqual(["shopmind-orders", "demo-user"]);
    expect(keys).toContainEqual(["shopmind-payments", "demo-user", "order-1"]);
    expect(keys.some((key) => key?.[0] === "shopmind-cart")).toBe(false);
  });

  it("preserves A recovery across A to B to A while isolating B", async () => {
    const existing = newPaymentSubmission("demo-user", "order-1");
    updatePaymentSubmission(existing, "unknown", "attempt-1");
    function IdentityHarness() {
      const { setUserId, userId } = useSession();
      return <><button onClick={() => setUserId(userId === "demo-user" ? "user-b" : "demo-user")} type="button">Switch identity</button><PaymentSection backendUserId={userId} identity={userId} order={order()} paymentQuery={paymentQuery()} /></>;
    }
    const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    render(<QueryClientProvider client={client}><SessionProvider><IdentityHarness /></SessionProvider></QueryClientProvider>);
    expect(await screen.findByTestId("payment-status-unknown")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Switch identity" }));
    await waitFor(() => expect(screen.queryByTestId("payment-status-unknown")).not.toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Mock Payment" })).toBeInTheDocument();
    expect(readPaymentSubmission("user-b", "order-1")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Switch identity" }));
    expect(await screen.findByTestId("payment-status-unknown")).toBeInTheDocument();
    expect(readPaymentSubmission("demo-user", "order-1")?.idempotencyKey).toBe(existing.idempotencyKey);
  });

  it("discards a payment_in_progress submission and permits a new explicit attempt after failure", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ code: "payment_in_progress", message: "Payment is already in progress", details: {}, idempotent_replay: false }, 409))
      .mockResolvedValueOnce(jsonResponse(paymentResponse("succeeded", "paid")));
    const view = renderSection(fetchMock);

    fireEvent.click(screen.getByRole("button", { name: "Mock Payment" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(readPaymentSubmission("demo-user", "order-1")).toBeNull();

    view.rerender(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}><SessionProvider><PaymentSection backendUserId="demo-user" identity="demo-user" order={order()} paymentQuery={paymentQuery([attempt("failed")])} /></SessionProvider></QueryClientProvider>);
    expect(screen.getByRole("button", { name: "Mock Payment" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Mock Payment" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const firstKey = new Headers((fetchMock.mock.calls[0]?.[1] as RequestInit).headers).get("Idempotency-Key");
    const secondKey = new Headers((fetchMock.mock.calls[1]?.[1] as RequestInit).headers).get("Idempotency-Key");
    expect(firstKey).not.toBe(secondKey);
  });

  it("discards an idempotency conflict without auto-retrying and starts a new key only on explicit action", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ code: "idempotency_conflict", message: "conflict", details: {}, idempotent_replay: false }, 409))
      .mockResolvedValueOnce(jsonResponse(paymentResponse("succeeded", "paid")));
    renderSection(fetchMock);

    fireEvent.click(screen.getByRole("button", { name: "Mock Payment" }));
    await waitFor(() => expect(screen.getByTestId("payment-idempotency-conflict")).toBeInTheDocument());
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(readPaymentSubmission("demo-user", "order-1")).toBeNull();
    expect(screen.getByTestId("payment-idempotency-conflict")).toHaveTextContent("Automatic retry stopped");

    fireEvent.click(screen.getByRole("button", { name: "Mock Payment" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const firstKey = new Headers((fetchMock.mock.calls[0]?.[1] as RequestInit).headers).get("Idempotency-Key");
    const secondKey = new Headers((fetchMock.mock.calls[1]?.[1] as RequestInit).headers).get("Idempotency-Key");
    expect(firstKey).not.toBe(secondKey);
  });
});
