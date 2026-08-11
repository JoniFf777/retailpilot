import { createId } from "../../app/id";

export type CheckoutSubmissionState = "ready" | "unknown" | "succeeded";

export interface CheckoutAttempt {
  attemptId: string;
  checkoutToken: string;
  idempotencyKey: string;
  identity: string;
  submissionState: CheckoutSubmissionState;
}

const STORAGE_PREFIX = "shopmind-checkout-attempt:";

function storageKey(identity: string): string {
  return `${STORAGE_PREFIX}${encodeURIComponent(identity)}`;
}

function readStorage(identity: string): CheckoutAttempt | null {
  if (typeof sessionStorage === "undefined") return null;
  try {
    const raw = sessionStorage.getItem(storageKey(identity));
    if (!raw) return null;
    const value = JSON.parse(raw) as Partial<CheckoutAttempt>;
    if (value.identity !== identity || typeof value.attemptId !== "string" || typeof value.checkoutToken !== "string" || typeof value.idempotencyKey !== "string" || !["ready", "unknown", "succeeded"].includes(value.submissionState ?? "")) return null;
    return value as CheckoutAttempt;
  } catch {
    return null;
  }
}

function writeStorage(attempt: CheckoutAttempt): void {
  if (typeof sessionStorage === "undefined") return;
  try {
    if (attempt.submissionState === "unknown") sessionStorage.setItem(storageKey(attempt.identity), JSON.stringify(attempt));
    else sessionStorage.removeItem(storageKey(attempt.identity));
  } catch { /* storage is optional */ }
}

export function newCheckoutAttempt(identity: string, checkoutToken: string): CheckoutAttempt {
  const attempt = { attemptId: createId("checkout"), checkoutToken, idempotencyKey: createId("request"), identity, submissionState: "ready" as const };
  writeStorage(attempt);
  return attempt;
}

export function readCheckoutAttempt(identity: string): CheckoutAttempt | null { return readStorage(identity); }

export function updateCheckoutAttempt(attempt: CheckoutAttempt, submissionState: CheckoutSubmissionState): CheckoutAttempt {
  const updated = { ...attempt, submissionState };
  writeStorage(updated);
  return updated;
}

export function clearCheckoutAttempt(identity: string): void {
  if (typeof sessionStorage === "undefined") return;
  try { sessionStorage.removeItem(storageKey(identity)); } catch { /* storage is optional */ }
}

export function clearAllCheckoutAttempts(): void {
  if (typeof sessionStorage === "undefined") return;
  try {
    for (let index = sessionStorage.length - 1; index >= 0; index -= 1) {
      const key = sessionStorage.key(index);
      if (key?.startsWith(STORAGE_PREFIX)) sessionStorage.removeItem(key);
    }
  } catch { /* storage is optional */ }
}
