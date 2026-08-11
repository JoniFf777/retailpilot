import { beforeEach, describe, expect, it } from "vitest";
import { clearAllPaymentSubmissions, newPaymentSubmission, readPaymentSubmission, updatePaymentSubmission } from "./paymentAttempt";

describe("Payment submission persistence", () => {
  beforeEach(() => clearAllPaymentSubmissions());

  it("creates one fixed Mock Payment body and persists the logical key", () => {
    const submission = newPaymentSubmission("user-a", "order-1");
    expect(submission.request).toEqual({ provider: "mock", payment_method_ref: "mock-web" });
    expect(submission.idempotencyKey).toBeTruthy();
    expect(readPaymentSubmission("user-a", "order-1")).toEqual(submission);
    expect(localStorage.getItem("shopmind-payment-attempt:user-a:order-1")).toContain(submission.idempotencyKey);
  });

  it("updates unknown/recovery state without changing the key or body", () => {
    const submission = newPaymentSubmission("user-a", "order-1");
    const updated = updatePaymentSubmission(submission, "unknown", "attempt-1");
    expect(updated.idempotencyKey).toBe(submission.idempotencyKey);
    expect(updated.request).toEqual(submission.request);
    expect(readPaymentSubmission("user-a", "order-1")).toEqual(updated);
  });

  it("scopes state by identity and creates a new key only for a new attempt", () => {
    const first = newPaymentSubmission("user-a", "order-1");
    const second = newPaymentSubmission("user-a", "order-1");
    expect(second.idempotencyKey).not.toBe(first.idempotencyKey);
    expect(readPaymentSubmission("user-b", "order-1")).toBeNull();
  });
});
