import type { PaymentAttemptRequest, PaymentAttemptStatus } from "../../api/contracts";

export type PaymentSubmissionState =
  | "ready"
  | "processing"
  | "unknown"
  | "provider_unavailable"
  | "provider_succeeded"
  | "finalization_pending"
  | "failed"
  | "conflict"
  | "succeeded";

export interface PaymentSubmission {
  identity: string;
  orderId: string;
  request: PaymentAttemptRequest;
  idempotencyKey: string;
  submissionState: PaymentSubmissionState;
  attemptId?: string;
}

const STORAGE_PREFIX = "shopmind-payment-attempt:";
const MOCK_PAYMENT_REQUEST: PaymentAttemptRequest = { provider: "mock", payment_method_ref: "mock-web" };

function storageKey(identity: string, orderId: string): string {
  return `${STORAGE_PREFIX}${encodeURIComponent(identity)}:${encodeURIComponent(orderId)}`;
}

function isPaymentStatus(value: unknown): value is PaymentAttemptStatus {
  return value === "processing" || value === "unknown" || value === "provider_succeeded" || value === "failed" || value === "succeeded";
}

function isSubmissionState(value: unknown): value is PaymentSubmissionState {
  return value === "ready" || value === "provider_unavailable" || value === "finalization_pending" || value === "conflict" || isPaymentStatus(value);
}

function paymentStorage(): Storage | null {
  if (typeof localStorage === "undefined") return null;
  try {
    return localStorage;
  } catch {
    return null;
  }
}

function readStorage(identity: string, orderId: string): PaymentSubmission | null {
  const storage = paymentStorage();
  if (!storage) return null;
  try {
    const raw = storage.getItem(storageKey(identity, orderId));
    if (!raw) return null;
    const value = JSON.parse(raw) as Partial<PaymentSubmission>;
    const request = value.request as Partial<PaymentAttemptRequest> | undefined;
    if (value.identity !== identity || value.orderId !== orderId || typeof value.idempotencyKey !== "string" || !isSubmissionState(value.submissionState) || request?.provider !== "mock" || request.payment_method_ref !== "mock-web") return null;
    return value as PaymentSubmission;
  } catch {
    return null;
  }
}

function writeStorage(submission: PaymentSubmission): void {
  const storage = paymentStorage();
  if (!storage) return;
  try {
    storage.setItem(storageKey(submission.identity, submission.orderId), JSON.stringify(submission));
  } catch { /* storage is optional */ }
}

function newKey(): string {
  return typeof crypto.randomUUID === "function" ? crypto.randomUUID() : `payment-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export function newPaymentSubmission(identity: string, orderId: string): PaymentSubmission {
  const submission: PaymentSubmission = {
    identity,
    orderId,
    request: { ...MOCK_PAYMENT_REQUEST },
    idempotencyKey: newKey(),
    submissionState: "ready",
  };
  writeStorage(submission);
  return submission;
}

export function readPaymentSubmission(identity: string, orderId: string): PaymentSubmission | null {
  return readStorage(identity, orderId);
}

export function updatePaymentSubmission(submission: PaymentSubmission, submissionState: PaymentSubmissionState, attemptId?: string): PaymentSubmission {
  const updated = { ...submission, submissionState, ...(attemptId ? { attemptId } : {}) };
  writeStorage(updated);
  return updated;
}

export function clearPaymentSubmission(identity: string, orderId: string): void {
  const storage = paymentStorage();
  if (!storage) return;
  try { storage.removeItem(storageKey(identity, orderId)); } catch { /* storage is optional */ }
}

export function clearAllPaymentSubmissions(): void {
  const storage = paymentStorage();
  if (!storage) return;
  try {
    for (let index = storage.length - 1; index >= 0; index -= 1) {
      const key = storage.key(index);
      if (key?.startsWith(STORAGE_PREFIX)) storage.removeItem(key);
    }
  } catch { /* storage is optional */ }
}
