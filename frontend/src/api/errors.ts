import type { ActionErrorResponse, ApiErrorBody, CartErrorDetails, CartErrorResponse, CheckoutErrorResponse, OrderErrorResponse, PaymentErrorResponse } from "./contracts";

const CART_ERROR_CODES = new Set<CartErrorResponse["code"]>([
  "cart_item_not_found", "cart_version_conflict", "invalid_quantity", "cart_quantity_limit",
  "insufficient_inventory", "product_inactive", "sku_inactive", "catalog_not_found", "inventory_missing",
]);

const CART_ERROR_DETAIL_KEYS: Array<keyof CartErrorDetails> = [
  "available_quantity", "current_quantity", "requested_quantity", "max_quantity", "current_version",
];

const ORDER_ERROR_CODES = new Set<OrderErrorResponse["code"]>([
  "checkout_invalid", "checkout_expired", "checkout_unavailable", "cart_changed", "mixed_currency",
  "product_inactive", "sku_inactive", "inventory_missing", "insufficient_inventory", "price_changed",
  "idempotency_conflict", "order_not_found", "reservation_inconsistent", "idempotency_key_invalid", "cursor_invalid",
]);

const PAYMENT_ERROR_CODES = new Set<PaymentErrorResponse["code"]>([
  "idempotency_key_invalid", "idempotency_conflict", "order_not_found", "order_not_payable",
  "order_already_paid", "payment_in_progress", "payment_declined", "payment_provider_unavailable",
  "payment_finalization_pending",
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function isCartErrorDetails(value: unknown): value is CartErrorDetails {
  if (value === undefined) return true;
  if (!isRecord(value)) return false;
  return CART_ERROR_DETAIL_KEYS.every((key) => {
    const candidate = value[key];
    return candidate === undefined || (typeof candidate === "number" && Number.isFinite(candidate));
  });
}

export function readCartError(value: unknown): CartErrorResponse | null {
  if (!isRecord(value)) return null;
  const candidate = value.code !== undefined ? value : isRecord(value.detail) ? value.detail : null;
  if (!candidate || typeof candidate.code !== "string" || !CART_ERROR_CODES.has(candidate.code as CartErrorResponse["code"]) || typeof candidate.message !== "string" || !isCartErrorDetails(candidate.details)) {
    return null;
  }
  return {
    code: candidate.code as CartErrorResponse["code"],
    message: candidate.message,
    ...(candidate.details === undefined ? {} : { details: candidate.details }),
  };
}

function isApiErrorBody(value: unknown): value is ApiErrorBody {
  return isRecord(value) && "detail" in value && (typeof value.detail === "string" || Array.isArray(value.detail) || isRecord(value.detail));
}

export class ApiError extends Error {
  readonly status: number;
  readonly requestId: string | null;
  readonly body: ApiErrorBody | null;
  readonly actionError: ActionErrorResponse | null;
  readonly cartError: CartErrorResponse | null;
  readonly checkoutError: CheckoutErrorResponse | null;
  readonly orderError: OrderErrorResponse | null;
  readonly paymentError: PaymentErrorResponse | null;

  constructor(message: string, status: number, body: ApiErrorBody | null, requestId: string | null, actionError: ActionErrorResponse | null = null, cartError: CartErrorResponse | null = null, checkoutError: CheckoutErrorResponse | null = null, orderError: OrderErrorResponse | null = null, paymentError: PaymentErrorResponse | null = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
    this.requestId = requestId;
    this.actionError = actionError;
    this.cartError = cartError;
    this.checkoutError = checkoutError;
    this.orderError = orderError;
    this.paymentError = paymentError;
  }
}

export async function readApiError(response: Response): Promise<ApiError> {
  let rawBody: unknown = null;
  try {
    rawBody = await response.json();
  } catch {
    rawBody = null;
  }

  const body = isApiErrorBody(rawBody) ? rawBody : null;
  const cartError = readCartError(rawBody);
  const orderError = readOrderError(rawBody);
  const paymentError = readPaymentError(rawBody);
  const checkoutError = readCheckoutError(rawBody);
  const detail: unknown = isRecord(rawBody) && "detail" in rawBody ? rawBody.detail : rawBody;
  const actionError = readActionError(rawBody);
  const message = typeof detail === "string"
    ? detail
    : Array.isArray(detail)
      ? detail.map((item) => item.msg ?? "Invalid request").join("; ")
      : detail && typeof detail === "object" && "message" in detail && typeof detail.message === "string"
        ? detail.message
        : "ShopMind request failed.";

  return new ApiError(paymentError?.message ?? orderError?.message ?? checkoutError?.message ?? cartError?.message ?? actionError?.message ?? message, response.status, body, response.headers.get("x-request-id"), actionError, cartError, checkoutError, orderError, paymentError);
}

function readOrderError(value: unknown): OrderErrorResponse | null {
  if (!isRecord(value)) return null;
  const candidate = value.code !== undefined ? value : isRecord(value.detail) ? value.detail : null;
  if (!isRecord(candidate) || typeof candidate.code !== "string" || !ORDER_ERROR_CODES.has(candidate.code as OrderErrorResponse["code"]) || typeof candidate.message !== "string") return null;
  return candidate as OrderErrorResponse;
}

function readCheckoutError(value: unknown): CheckoutErrorResponse | null {
  const candidate = readOrderError(value);
  return candidate?.code === "checkout_unavailable" ? candidate as CheckoutErrorResponse : null;
}

function readPaymentError(value: unknown): PaymentErrorResponse | null {
  if (!isRecord(value)) return null;
  const candidate = value.code !== undefined ? value : isRecord(value.detail) ? value.detail : null;
  if (!isRecord(candidate) || typeof candidate.code !== "string" || !PAYMENT_ERROR_CODES.has(candidate.code as PaymentErrorResponse["code"]) || typeof candidate.message !== "string") return null;
  return candidate as PaymentErrorResponse;
}

const ACTION_ERROR_CODES = new Set([
  "pending_action_not_found", "recommendation_not_found", "sku_not_in_recommendation", "invalid_quantity",
  "invalid_updated_fields", "version_conflict", "action_resolution_conflict", "action_expired", "catalog_not_found",
  "catalog_identity_changed", "product_inactive", "sku_inactive", "insufficient_inventory", "cart_quantity_limit",
  "unsupported_action_schema", "invalid_action_payload",
]);

function readActionError(value: unknown): ActionErrorResponse | null {
  if (!value || typeof value !== "object") return null;
  const candidate = value as Record<string, unknown>;
  const direct = candidate.code !== undefined ? candidate : candidate.detail;
  if (!direct || typeof direct !== "object") return null;
  const item = direct as Record<string, unknown>;
  if (typeof item.code !== "string" || !ACTION_ERROR_CODES.has(item.code) || typeof item.message !== "string" || typeof item.details !== "object" || item.details === null || typeof item.idempotent_replay !== "boolean") return null;
  return item as ActionErrorResponse;
}
