import { beforeEach, describe, expect, it } from "vitest";
import { clearAllCheckoutAttempts, clearCheckoutAttempt, newCheckoutAttempt, readCheckoutAttempt, updateCheckoutAttempt } from "./checkoutAttempt";

describe("identity-scoped CheckoutAttempt", () => {
  beforeEach(() => sessionStorage.clear());

  it("persists one attempt with a stable token and idempotency key", () => {
    const attempt = newCheckoutAttempt("user-a", "checkout-token");
    expect(readCheckoutAttempt("user-a")).toBeNull();
    expect(attempt.attemptId).toMatch(/^checkout-/);
    expect(attempt.idempotencyKey).toMatch(/^request-/);
    const unknown = updateCheckoutAttempt(attempt, "unknown");
    expect(readCheckoutAttempt("user-a")).toEqual(unknown);
    expect(unknown).toMatchObject({
      attemptId: attempt.attemptId,
      checkoutToken: attempt.checkoutToken,
      idempotencyKey: attempt.idempotencyKey,
      identity: "user-a",
      submissionState: "unknown",
    });
  });

  it("never reads an attempt across identities and clears only the selected identity", () => {
    const userA = updateCheckoutAttempt(newCheckoutAttempt("user-a", "token-a"), "unknown");
    updateCheckoutAttempt(newCheckoutAttempt("user-b", "token-b"), "unknown");
    expect(readCheckoutAttempt("user-b")?.checkoutToken).toBe("token-b");
    clearCheckoutAttempt("user-a");
    expect(readCheckoutAttempt("user-a")).toBeNull();
    expect(readCheckoutAttempt("user-b")?.attemptId).not.toBe(userA.attemptId);
  });

  it("can clear all identity-scoped recovery records", () => {
    updateCheckoutAttempt(newCheckoutAttempt("user-a", "token-a"), "unknown");
    updateCheckoutAttempt(newCheckoutAttempt("user-b", "token-b"), "unknown");
    clearAllCheckoutAttempts();
    expect(readCheckoutAttempt("user-a")).toBeNull();
    expect(readCheckoutAttempt("user-b")).toBeNull();
  });
});
