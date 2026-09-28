import type {
  AddToCartPendingActionRequest,
  CartItemView,
  CartMutationResponse,
  CartResponse,
  CatalogBrowseAddToCartPendingActionRequest,
  CatalogProductSummary,
  CatalogSkuView,
  CheckoutPreview,
  CreateOrderResponse,
  OrderListResponse,
  OrderView,
  PaymentAttemptListResponse,
  PaymentAttemptResponse,
  PaymentAttemptView,
  PendingActionTransitionResponse,
  PendingActionView,
} from "../api/contracts";
import { findDemoSkuById } from "./fixtures/catalog";
import { DemoHttpError } from "./store";

function clone<T>(value: T): T {
  return structuredClone(value);
}

function money(amount: number): { amount: string; currency: string } {
  return { amount: amount.toFixed(2), currency: "CNY" };
}

function nowIso(): string {
  return new Date().toISOString();
}

type PendingActionRecord = {
  view: PendingActionView;
  skuId: string;
  quantity: number;
};

const CART_ID_PREFIX = "00000000-0000-4000-b000-";
const ORDER_ID_PREFIX = "00000000-0000-4000-d000-";
const PAYMENT_ID_PREFIX = "00000000-0000-4000-e000-";
const ACTION_ID_PREFIX = "00000000-0000-4000-f000-";

/** A single price-changed demo beat: confirming this SKU's pending action always reports
 *  a price 200 CNY higher than the snapshot shown when the action was created, exercising
 *  `PendingActionTransitionResponse.price_changed` end to end (§4's "确认前价格变动" scenario)
 *  even though the current UI doesn't yet render it distinctly from a normal confirmation. */
const PRICE_DRIFT_SKU_CODE = "TECH-LAP-003-A";

/** Cart, checkout, orders and payments share one lifecycle (a cart item becomes a checkout
 *  line becomes an order line becomes something a payment attempt is made against), so one
 *  store owns all four rather than splitting them — same reasoning as `DemoTaskStore` owning
 *  the whole task lifecycle instead of one class per endpoint. */
export class DemoCommerceStore {
  private readonly cart = new Map<string, CartItemView>();
  private readonly pendingActions = new Map<string, PendingActionRecord>();
  private readonly orders = new Map<string, OrderView>();
  private readonly payments = new Map<string, PaymentAttemptView[]>();
  private readonly checkoutTokens = new Map<string, string>();
  private readonly orderIdempotency = new Map<string, string>();
  private readonly paymentIdempotency = new Map<string, string>();
  private cartSuffix = 1;
  private actionSuffix = 1;
  private orderSuffix = 1;
  private paymentSuffix = 1;

  private createPendingAction(skuId: string, quantity: number): PendingActionView {
    const found = findDemoSkuById(skuId);
    if (!found) throw new DemoHttpError(404, "catalog_not_found");
    const actionId = `${ACTION_ID_PREFIX}${String(this.actionSuffix++).padStart(12, "0")}`;
    const view: PendingActionView = {
      pending_action_id: actionId,
      action_type: "add_to_cart",
      status: "pending",
      version: 1,
      risk_class: quantity > 3 ? "high" : "medium",
      confirm_label: "Confirm",
      cancel_label: "Cancel",
      expires_at: new Date(Date.now() + 15 * 60_000).toISOString(),
      editable_fields: [
        {
          field_type: "integer",
          field: "quantity",
          label: "Quantity",
          current_value: quantity,
          min_value: 1,
          max_value: 20,
          required: true,
        },
      ],
      preview: {
        kind: "catalog_sku",
        product_id: found.product.product_id,
        product_code: found.product.product_code,
        product_name: found.product.name,
        sku_id: found.sku.sku_id,
        sku_code: found.sku.sku_code,
        sku_name: found.sku.sku_name,
        requested_quantity: quantity,
        unit_money_snapshot: found.sku.money,
        subtotal_money_snapshot: money(Number(found.sku.money.amount) * quantity),
        availability_snapshot: found.sku.availability,
        preview_text: null,
      },
    };
    this.pendingActions.set(actionId, { view, skuId, quantity });
    return clone(view);
  }

  createAddToCartPendingAction(request: AddToCartPendingActionRequest): PendingActionView {
    return this.createPendingAction(request.sku_id, request.quantity ?? 1);
  }

  createCatalogBrowsePendingAction(
    request: CatalogBrowseAddToCartPendingActionRequest,
  ): PendingActionView {
    return this.createPendingAction(request.sku_id, request.quantity ?? 1);
  }

  getPendingAction(pendingActionId: string): PendingActionView {
    const record = this.pendingActions.get(pendingActionId);
    if (!record) throw new DemoHttpError(404, "pending_action_not_found");
    return clone(record.view);
  }

  confirmPendingAction(
    pendingActionId: string,
    expectedVersion: number,
    updatedQuantity?: number,
  ): PendingActionTransitionResponse {
    const record = this.pendingActions.get(pendingActionId);
    if (!record) throw new DemoHttpError(404, "pending_action_not_found");
    if (record.view.version !== expectedVersion) throw new DemoHttpError(409, "version_conflict");
    if (record.view.status !== "pending") throw new DemoHttpError(410, "action_expired");

    const found = findDemoSkuById(record.skuId);
    if (!found) throw new DemoHttpError(404, "catalog_not_found");
    const quantity = updatedQuantity ?? record.quantity;
    const snapshotUnit = Number(found.sku.money.amount);
    const priceChanged = found.sku.sku_code === PRICE_DRIFT_SKU_CODE;
    const currentUnit = priceChanged ? snapshotUnit + 200 : snapshotUnit;

    record.view.status = "confirmed";
    record.view.version += 1;

    const cartItem = this.upsertCartItem(found.product, found.sku, quantity, currentUnit);

    return {
      idempotent_replay: false,
      pending_action: clone(record.view),
      cart_item: clone(cartItem),
      cart_quantity: cartItem.quantity,
      price_changed: priceChanged,
      requested_quantity: quantity,
      current_money: money(currentUnit),
      snapshot_money: money(snapshotUnit),
    };
  }

  cancelPendingAction(
    pendingActionId: string,
    expectedVersion: number,
  ): PendingActionTransitionResponse {
    const record = this.pendingActions.get(pendingActionId);
    if (!record) throw new DemoHttpError(404, "pending_action_not_found");
    if (record.view.version !== expectedVersion) throw new DemoHttpError(409, "version_conflict");
    if (record.view.status !== "pending") throw new DemoHttpError(410, "action_expired");
    record.view.status = "cancelled";
    record.view.version += 1;
    return {
      idempotent_replay: false,
      pending_action: clone(record.view),
      price_changed: false,
    };
  }

  private upsertCartItem(
    product: CatalogProductSummary,
    sku: CatalogSkuView,
    quantity: number,
    unitAmount: number,
  ): CartItemView {
    const existing = [...this.cart.values()].find((item) => item.sku_id === sku.sku_id);
    const nextQuantity = (existing?.quantity ?? 0) + quantity;
    const cartItemId =
      existing?.cart_item_id ?? `${CART_ID_PREFIX}${String(this.cartSuffix++).padStart(12, "0")}`;
    const item: CartItemView = {
      cart_item_id: cartItemId,
      product_id: product.product_id,
      product_code: product.product_code,
      product_name: product.name,
      product_sale_status: "active",
      sku_id: sku.sku_id,
      sku_code: sku.sku_code,
      sku_name: sku.sku_name,
      sku_sale_status: "active",
      effective_sale_status: "active",
      quantity: nextQuantity,
      unit_money: money(unitAmount),
      subtotal_money: money(unitAmount * nextQuantity),
      availability: sku.availability,
      version: (existing?.version ?? 0) + 1,
      created_at: existing?.created_at ?? nowIso(),
      updated_at: nowIso(),
    };
    this.cart.set(cartItemId, item);
    return item;
  }

  getCart(): CartResponse {
    const items = [...this.cart.values()];
    const currencies = new Set(items.map((item) => item.unit_money.currency));
    const subtotalAmount = items.reduce((sum, item) => sum + Number(item.subtotal_money.amount), 0);
    return {
      items: items.map(clone),
      item_count: items.length,
      total_quantity: items.reduce((sum, item) => sum + item.quantity, 0),
      subtotal: currencies.size <= 1 ? money(subtotalAmount) : null,
      warnings:
        currencies.size > 1
          ? [{ code: "mixed_currency", message: "购物车包含不同币种，暂不计算合计。" }]
          : [],
    };
  }

  updateCartItem(
    cartItemId: string,
    expectedVersion: number,
    quantity: number,
  ): CartMutationResponse {
    const item = this.cart.get(cartItemId);
    if (!item) throw new DemoHttpError(404, "cart_item_not_found");
    if (item.version !== expectedVersion) throw new DemoHttpError(409, "cart_version_conflict");
    if (quantity < 1 || quantity > 20) throw new DemoHttpError(422, "invalid_quantity");
    item.quantity = quantity;
    item.subtotal_money = money(Number(item.unit_money.amount) * quantity);
    item.version += 1;
    item.updated_at = nowIso();
    return { cart: this.getCart(), item: clone(item) };
  }

  deleteCartItem(cartItemId: string): void {
    if (!this.cart.delete(cartItemId)) throw new DemoHttpError(404, "cart_item_not_found");
  }

  clearCart(): void {
    this.cart.clear();
  }

  checkoutPreview(): CheckoutPreview {
    const items = [...this.cart.values()];
    const token = `00000000-0000-4000-9000-${String(this.orderSuffix).padStart(12, "0")}`;
    this.checkoutTokens.set(token, token);
    const currencies = new Set(items.map((item) => item.unit_money.currency));
    const subtotalAmount = items.reduce((sum, item) => sum + Number(item.subtotal_money.amount), 0);
    return {
      checkout_token: items.length > 0 ? token : null,
      can_create_order: items.length > 0,
      revalidation_required: true,
      currency: currencies.size === 1 ? [...currencies][0] : null,
      item_count: items.length,
      total_quantity: items.reduce((sum, item) => sum + item.quantity, 0),
      subtotal: currencies.size <= 1 ? money(subtotalAmount) : null,
      expires_at: new Date(Date.now() + 10 * 60_000).toISOString(),
      items: items.map((item) => ({
        cart_item_id: item.cart_item_id,
        sku_id: item.sku_id,
        sku_name: item.sku_name,
        product_name: item.product_name,
        quantity: item.quantity,
        unit_money: item.unit_money,
        subtotal_money: item.subtotal_money,
        availability: item.availability,
        version: item.version,
      })),
      warnings: [],
    };
  }

  createOrder(checkoutToken: string, idempotencyKey: string): CreateOrderResponse {
    const existingOrderId = this.orderIdempotency.get(idempotencyKey);
    if (existingOrderId) {
      const order = this.orders.get(existingOrderId);
      if (order) return { idempotent_replay: true, order: clone(order) };
    }
    if (!this.checkoutTokens.has(checkoutToken)) throw new DemoHttpError(409, "checkout_expired");
    const items = [...this.cart.values()];
    if (items.length === 0) throw new DemoHttpError(409, "cart_changed");

    const orderId = `${ORDER_ID_PREFIX}${String(this.orderSuffix++).padStart(12, "0")}`;
    const subtotalAmount = items.reduce((sum, item) => sum + Number(item.subtotal_money.amount), 0);
    const order: OrderView = {
      order_id: orderId,
      status: "pending_payment",
      currency: items[0]?.unit_money.currency ?? "CNY",
      subtotal: money(subtotalAmount),
      total: money(subtotalAmount),
      version: 1,
      created_at: nowIso(),
      updated_at: nowIso(),
      expires_at: new Date(Date.now() + 30 * 60_000).toISOString(),
      items: items.map((item, index) => ({
        item_id: `${ORDER_ID_PREFIX}i${String(index).padStart(11, "0")}`,
        product_code: item.product_code,
        product_name: item.product_name,
        sku_id: item.sku_id,
        sku_code: item.sku_code,
        sku_name: item.sku_name,
        quantity: item.quantity,
        unit_money: item.unit_money,
        subtotal_money: item.subtotal_money,
      })),
    };
    this.orders.set(orderId, order);
    this.orderIdempotency.set(idempotencyKey, orderId);
    this.checkoutTokens.delete(checkoutToken);
    this.cart.clear();
    return { idempotent_replay: false, order: clone(order) };
  }

  listOrders(): OrderListResponse {
    const items = [...this.orders.values()].sort((a, b) =>
      b.created_at.localeCompare(a.created_at),
    );
    return { items: items.map(clone), next_cursor: null };
  }

  getOrder(orderId: string): OrderView {
    const order = this.orders.get(orderId);
    if (!order) throw new DemoHttpError(404, "order_not_found");
    return clone(order);
  }

  cancelOrder(orderId: string): { idempotent_replay: boolean; order: OrderView } {
    const order = this.orders.get(orderId);
    if (!order) throw new DemoHttpError(404, "order_not_found");
    if (order.status === "cancelled") return { idempotent_replay: true, order: clone(order) };
    if (order.status !== "pending_payment") throw new DemoHttpError(409, "order_not_cancellable");
    order.status = "cancelled";
    order.version += 1;
    order.updated_at = nowIso();
    return { idempotent_replay: false, order: clone(order) };
  }

  createPayment(orderId: string, idempotencyKey: string): PaymentAttemptResponse {
    const order = this.orders.get(orderId);
    if (!order) throw new DemoHttpError(404, "order_not_found");
    const existingAttemptId = this.paymentIdempotency.get(idempotencyKey);
    if (existingAttemptId) {
      const attempts = this.payments.get(orderId) ?? [];
      const attempt = attempts.find((item) => item.attempt_id === existingAttemptId);
      if (attempt)
        return { idempotent_replay: true, order: clone(order), payment_attempt: clone(attempt) };
    }
    if (order.status === "paid") throw new DemoHttpError(409, "order_already_paid");
    if (order.status !== "pending_payment") throw new DemoHttpError(409, "order_not_payable");

    const attemptId = `${PAYMENT_ID_PREFIX}${String(this.paymentSuffix++).padStart(12, "0")}`;
    const attempt: PaymentAttemptView = {
      attempt_id: attemptId,
      order_id: orderId,
      provider: "mock",
      status: "succeeded",
      created_at: nowIso(),
      updated_at: nowIso(),
      completed_at: nowIso(),
      failure_code: null,
      provider_result_at: nowIso(),
      amount: order.total,
    };
    const attempts = this.payments.get(orderId) ?? [];
    attempts.push(attempt);
    this.payments.set(orderId, attempts);
    this.paymentIdempotency.set(idempotencyKey, attemptId);

    order.status = "paid";
    order.version += 1;
    order.updated_at = nowIso();

    return { idempotent_replay: false, order: clone(order), payment_attempt: clone(attempt) };
  }

  listPayments(orderId: string): PaymentAttemptListResponse {
    if (!this.orders.has(orderId)) throw new DemoHttpError(404, "order_not_found");
    return { items: (this.payments.get(orderId) ?? []).map(clone) };
  }
}
