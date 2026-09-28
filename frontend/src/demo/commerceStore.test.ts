import { describe, expect, it } from "vitest";
import { DemoCommerceStore } from "./commerceStore";
import { DemoHttpError } from "./store";
import { DEMO_PRODUCTS } from "./fixtures/catalog";

const LAPTOP_A_SKU = DEMO_PRODUCTS.laptop[0]!.skus[0]!.sku_id;
const LAPTOP_B_SKU = DEMO_PRODUCTS.laptop[1]!.skus[0]!.sku_id;

function confirmedCart(store: DemoCommerceStore, skuId: string, quantity = 1) {
  const action = store.createAddToCartPendingAction({
    sku_id: skuId,
    quantity,
    source_run_id: "run-1",
    thread_id: "thread-1",
  });
  return store.confirmPendingAction(action.pending_action_id, action.version);
}

describe("DemoCommerceStore", () => {
  it("creates a pending action referencing the real catalog SKU", () => {
    const store = new DemoCommerceStore();
    const action = store.createAddToCartPendingAction({
      sku_id: LAPTOP_A_SKU,
      quantity: 2,
      source_run_id: "run-1",
      thread_id: "thread-1",
    });
    expect(action.status).toBe("pending");
    expect(action.action_type).toBe("add_to_cart");
    expect(store.getPendingAction(action.pending_action_id)).toEqual(action);
  });

  it("throws a 404 for an unknown SKU", () => {
    const store = new DemoCommerceStore();
    expect(() =>
      store.createAddToCartPendingAction({
        sku_id: "does-not-exist",
        quantity: 1,
        source_run_id: "run-1",
        thread_id: "thread-1",
      }),
    ).toThrow(DemoHttpError);
  });

  it("confirming a pending action adds the item to the cart", () => {
    const store = new DemoCommerceStore();
    const resolution = confirmedCart(store, LAPTOP_A_SKU, 2);
    expect(resolution.pending_action.status).toBe("confirmed");
    expect(resolution.cart_quantity).toBe(2);
    const cart = store.getCart();
    expect(cart.item_count).toBe(1);
    expect(cart.total_quantity).toBe(2);
    expect(cart.items?.[0]?.sku_id).toBe(LAPTOP_A_SKU);
  });

  it("confirming the same SKU twice merges into one cart line", () => {
    const store = new DemoCommerceStore();
    confirmedCart(store, LAPTOP_A_SKU, 1);
    confirmedCart(store, LAPTOP_A_SKU, 2);
    const cart = store.getCart();
    expect(cart.item_count).toBe(1);
    expect(cart.items?.[0]?.quantity).toBe(3);
  });

  it("rejects confirming a pending action twice (already terminal)", () => {
    const store = new DemoCommerceStore();
    const action = store.createAddToCartPendingAction({
      sku_id: LAPTOP_A_SKU,
      quantity: 1,
      source_run_id: "run-1",
      thread_id: "thread-1",
    });
    store.confirmPendingAction(action.pending_action_id, action.version);
    expect(() => store.confirmPendingAction(action.pending_action_id, action.version + 1)).toThrow(
      DemoHttpError,
    );
  });

  it("cancelling a pending action leaves the cart untouched", () => {
    const store = new DemoCommerceStore();
    const action = store.createAddToCartPendingAction({
      sku_id: LAPTOP_A_SKU,
      quantity: 1,
      source_run_id: "run-1",
      thread_id: "thread-1",
    });
    const resolution = store.cancelPendingAction(action.pending_action_id, action.version);
    expect(resolution.pending_action.status).toBe("cancelled");
    expect(store.getCart().item_count).toBe(0);
  });

  it("updates cart quantity with the expected version and rejects a stale one", () => {
    const store = new DemoCommerceStore();
    confirmedCart(store, LAPTOP_A_SKU, 1);
    const item = store.getCart().items![0]!;
    expect(() => store.updateCartItem(item.cart_item_id, 99, 3)).toThrow(DemoHttpError);
    const mutation = store.updateCartItem(item.cart_item_id, item.version, 3);
    expect(mutation.item.quantity).toBe(3);
    expect(Number(mutation.item.subtotal_money.amount)).toBeCloseTo(
      Number(mutation.item.unit_money.amount) * 3,
      2,
    );
  });

  it("deletes and clears cart items", () => {
    const store = new DemoCommerceStore();
    confirmedCart(store, LAPTOP_A_SKU, 1);
    confirmedCart(store, LAPTOP_B_SKU, 1);
    const [first] = store.getCart().items!;
    store.deleteCartItem(first!.cart_item_id);
    expect(store.getCart().item_count).toBe(1);
    store.clearCart();
    expect(store.getCart().item_count).toBe(0);
  });

  it("checkout preview reflects the current cart and can create an order that clears it", () => {
    const store = new DemoCommerceStore();
    confirmedCart(store, LAPTOP_A_SKU, 1);
    const preview = store.checkoutPreview();
    expect(preview.can_create_order).toBe(true);
    expect(preview.item_count).toBe(1);
    expect(preview.checkout_token).toBeTruthy();

    const { order, idempotent_replay } = store.createOrder(preview.checkout_token!, "key-1");
    expect(idempotent_replay).toBe(false);
    expect(order.status).toBe("pending_payment");
    expect(order.items).toHaveLength(1);
    expect(store.getCart().item_count).toBe(0);
    expect(store.getOrder(order.order_id)).toEqual(order);
  });

  it("replays the same order for a repeated idempotency key instead of creating a second one", () => {
    const store = new DemoCommerceStore();
    confirmedCart(store, LAPTOP_A_SKU, 1);
    const preview = store.checkoutPreview();
    const first = store.createOrder(preview.checkout_token!, "same-key");
    confirmedCart(store, LAPTOP_B_SKU, 1);
    const second = store.createOrder(preview.checkout_token!, "same-key");
    expect(second.idempotent_replay).toBe(true);
    expect(second.order.order_id).toBe(first.order.order_id);
    expect(store.listOrders().items).toHaveLength(1);
  });

  it("rejects creating an order from an expired/unknown checkout token", () => {
    const store = new DemoCommerceStore();
    confirmedCart(store, LAPTOP_A_SKU, 1);
    expect(() => store.createOrder("not-a-real-token", "key-1")).toThrow(DemoHttpError);
  });

  it("cancels a pending order and rejects cancelling twice with a conflict", () => {
    const store = new DemoCommerceStore();
    confirmedCart(store, LAPTOP_A_SKU, 1);
    const preview = store.checkoutPreview();
    const { order } = store.createOrder(preview.checkout_token!, "key-1");
    const cancelled = store.cancelOrder(order.order_id);
    expect(cancelled.order.status).toBe("cancelled");
    const replay = store.cancelOrder(order.order_id);
    expect(replay.idempotent_replay).toBe(true);
  });

  it("creates a mock payment that pays the order, and replays on the same idempotency key", () => {
    const store = new DemoCommerceStore();
    confirmedCart(store, LAPTOP_A_SKU, 1);
    const preview = store.checkoutPreview();
    const { order } = store.createOrder(preview.checkout_token!, "order-key");

    const first = store.createPayment(order.order_id, "pay-key");
    expect(first.payment_attempt.status).toBe("succeeded");
    expect(first.order.status).toBe("paid");

    const second = store.createPayment(order.order_id, "pay-key");
    expect(second.idempotent_replay).toBe(true);
    expect(second.payment_attempt.attempt_id).toBe(first.payment_attempt.attempt_id);

    expect(store.listPayments(order.order_id).items).toHaveLength(1);
  });

  it("rejects a payment against an already-paid order with a new idempotency key", () => {
    const store = new DemoCommerceStore();
    confirmedCart(store, LAPTOP_A_SKU, 1);
    const preview = store.checkoutPreview();
    const { order } = store.createOrder(preview.checkout_token!, "order-key");
    store.createPayment(order.order_id, "pay-key-1");
    expect(() => store.createPayment(order.order_id, "pay-key-2")).toThrow(DemoHttpError);
  });
});
