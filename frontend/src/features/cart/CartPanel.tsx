import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../../api/errors";
import type { CartResponse, CartWarning, CartItemView } from "../../api/contracts";
import { shopMindApi } from "../../api/client";
import { useSession } from "../../app/useSession";
import { cn } from "../../components/cn";
import { BUTTON_DANGER, BUTTON_PRIMARY } from "../../components/textPatterns";
import { clearCheckoutAttempt } from "../checkout/checkoutAttempt";
import { checkoutPreviewQueryKey } from "../checkout/checkoutQuery";
import { CartConfirmationDialog } from "./CartConfirmationDialog";
import { CartItem } from "./CartItem";
import { cartErrorMessage, cartWarningMessage, insufficientInventoryMessage } from "./cartErrors";
import { formatMoney } from "./cartFormatters";
import { cartQueryKey } from "./cartQuery";
import { MAX_CART_QUANTITY, MIN_CART_QUANTITY, validateCartQuantity } from "./quantity";

type Confirmation = { kind: "delete"; cartItemId: string; productName: string } | { kind: "clear" };

function itemWarnings(warnings: CartWarning[], item: CartItemView): CartWarning[] {
  return warnings.filter((warning) => warning.cart_item_id === item.cart_item_id);
}

function mutationErrorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return "购物车操作失败，请稍后重试。";
  if (!error.cartError) return "购物车操作失败，请稍后重试。";
  if (error.cartError.code === "insufficient_inventory")
    return insufficientInventoryMessage(error.cartError);
  return cartErrorMessage(error.cartError);
}

function cartError(error: unknown): ApiError["cartError"] {
  return error instanceof ApiError ? error.cartError : null;
}

export function CartPanel({
  enabled = true,
  onCheckout,
}: {
  enabled?: boolean;
  onCheckout?: () => void;
}) {
  const { isDevelopment, userId } = useSession();
  const identity = isDevelopment ? userId.trim() : "trusted";
  const queryClient = useQueryClient();
  const queryKey = cartQueryKey(identity);
  const query = useQuery({
    queryKey,
    queryFn: ({ signal }) => shopMindApi.getCart(isDevelopment ? identity : undefined, signal),
    enabled: enabled && Boolean(identity),
    staleTime: 10_000,
    retry: false,
  });
  const [draftQuantities, setDraftQuantities] = useState<Record<string, string>>({});
  const [itemErrors, setItemErrors] = useState<Record<string, string | null>>({});
  const [clearError, setClearError] = useState<string | null>(null);
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const previousIdentity = useRef(identity);
  const restoreFocus = useRef<HTMLElement | null>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    if (previousIdentity.current === identity) return;
    previousIdentity.current = identity;
    setDraftQuantities({});
    setItemErrors({});
    setClearError(null);
    setConfirmation(null);
  }, [identity]);

  useEffect(() => {
    const items = query.data?.items ?? [];
    const ids = new Set(items.map((item) => item.cart_item_id));
    setDraftQuantities((current) => {
      const next: Record<string, string> = {};
      let changed = false;
      for (const item of items) {
        next[item.cart_item_id] = current[item.cart_item_id] ?? String(item.quantity);
        if (next[item.cart_item_id] !== current[item.cart_item_id]) changed = true;
      }
      for (const key of Object.keys(current)) if (!ids.has(key)) changed = true;
      return changed || Object.keys(current).length !== items.length ? next : current;
    });
    setItemErrors((current) => {
      const next = Object.fromEntries(Object.entries(current).filter(([key]) => ids.has(key)));
      return Object.keys(next).length === Object.keys(current).length ? current : next;
    });
  }, [query.data?.items]);

  const invalidateCart = useCallback(
    () => queryClient.invalidateQueries({ queryKey }),
    [queryClient, queryKey],
  );
  const clearCheckoutState = useCallback(() => {
    clearCheckoutAttempt(identity);
    queryClient.removeQueries({ queryKey: checkoutPreviewQueryKey(identity) });
  }, [identity, queryClient]);

  const updateMutation = useMutation({
    mutationFn: ({ item, quantity }: { item: CartItemView; quantity: number }) =>
      shopMindApi.updateCartItem(item.cart_item_id, { expected_version: item.version, quantity }),
    retry: false,
    onMutate: clearCheckoutState,
    onSuccess: async (result, { item }) => {
      setDraftQuantities((current) => ({
        ...current,
        [item.cart_item_id]: String(result.item.quantity),
      }));
      setItemErrors((current) => ({ ...current, [item.cart_item_id]: null }));
      queryClient.setQueryData(queryKey, result.cart);
      await invalidateCart();
    },
    onError: async (error, { item }) => {
      const typedError = cartError(error);
      if (
        typedError &&
        [
          "cart_version_conflict",
          "cart_item_not_found",
          "product_inactive",
          "sku_inactive",
          "catalog_not_found",
          "inventory_missing",
        ].includes(typedError.code)
      ) {
        await queryClient.refetchQueries({ queryKey });
        const latest = queryClient.getQueryData<CartResponse>(queryKey);
        if (latest)
          setDraftQuantities(
            Object.fromEntries(
              (latest.items ?? []).map((latestItem) => [
                latestItem.cart_item_id,
                String(latestItem.quantity),
              ]),
            ),
          );
      }
      setItemErrors((current) => ({
        ...current,
        [item.cart_item_id]: mutationErrorMessage(error),
      }));
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (cartItemId: string) => shopMindApi.deleteCartItem(cartItemId),
    retry: false,
    onMutate: clearCheckoutState,
    onSuccess: async (_, cartItemId) => {
      setDraftQuantities((current) => {
        const next = { ...current };
        delete next[cartItemId];
        return next;
      });
      setItemErrors((current) => {
        const next = { ...current };
        delete next[cartItemId];
        return next;
      });
      await invalidateCart();
    },
    onError: (error, cartItemId) =>
      setItemErrors((current) => ({ ...current, [cartItemId]: mutationErrorMessage(error) })),
  });

  const clearMutation = useMutation({
    mutationFn: () => shopMindApi.clearCart(),
    retry: false,
    onMutate: clearCheckoutState,
    onSuccess: async () => {
      setClearError(null);
      setDraftQuantities({});
      setItemErrors({});
      await invalidateCart();
    },
    onError: (error) => setClearError(mutationErrorMessage(error)),
  });

  const closeConfirmation = useCallback(() => {
    setConfirmation(null);
    window.requestAnimationFrame(() => {
      if (restoreFocus.current?.isConnected) restoreFocus.current.focus();
      else titleRef.current?.focus();
    });
  }, []);

  function openDeleteConfirmation(item: CartItemView, trigger: HTMLElement) {
    restoreFocus.current = trigger;
    setConfirmation({
      kind: "delete",
      cartItemId: item.cart_item_id,
      productName: item.product_name,
    });
  }

  function openClearConfirmation(trigger: HTMLElement) {
    restoreFocus.current = trigger;
    setConfirmation({ kind: "clear" });
  }

  function confirmMutation() {
    if (!confirmation) return;
    const current = confirmation;
    closeConfirmation();
    if (current.kind === "delete") deleteMutation.mutate(current.cartItemId);
    else clearMutation.mutate();
  }

  function updateDraft(itemId: string, value: string) {
    setDraftQuantities((current) => ({ ...current, [itemId]: value }));
    setItemErrors((current) => ({ ...current, [itemId]: null }));
  }

  function stepDraft(item: CartItemView, delta: number) {
    const current = validateCartQuantity(
      draftQuantities[item.cart_item_id] ?? String(item.quantity),
    );
    if (!current.valid) return;
    const next = Math.min(MAX_CART_QUANTITY, Math.max(MIN_CART_QUANTITY, current.quantity + delta));
    updateDraft(item.cart_item_id, String(next));
  }

  function updateItem(item: CartItemView) {
    const draft = draftQuantities[item.cart_item_id] ?? String(item.quantity);
    const validation = validateCartQuantity(draft);
    if (!validation.valid) return;
    updateMutation.mutate({ item, quantity: validation.quantity });
  }

  const data = query.data;
  const items = data?.items ?? [];
  const warnings = data?.warnings ?? [];
  const itemCount = data?.item_count ?? items.length;
  const totalQuantity =
    data?.total_quantity ?? items.reduce((total, item) => total + item.quantity, 0);
  const clearBusy = clearMutation.isPending;
  const mixedCurrency = warnings.some((warning) => warning.code === "mixed_currency");

  return (
    <section
      className="shopmind-cart-panel relative mt-4 grid gap-2.5 rounded-md border border-solid border-border bg-surface p-3.5"
      aria-label="RetailPilot 购物车"
    >
      <div className="flex items-center justify-between">
        <h2
          className="m-0 text-[0.92rem] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
          ref={titleRef}
          tabIndex={-1}
        >
          RetailPilot 购物车
        </h2>
        <span className="text-xs text-text-muted">{itemCount} 个 SKU</span>
      </div>
      {query.isLoading && (
        <p className="m-0 text-[0.72rem] leading-relaxed text-text-muted" role="status">
          正在读取购物车…
        </p>
      )}
      {query.error && (
        <p className="m-0 text-[0.72rem] leading-relaxed text-danger" role="alert">
          购物车暂时无法读取。
        </p>
      )}
      {data && (
        <div
          className="grid grid-cols-3 gap-2.5 rounded-sm border border-solid border-border bg-surface-soft p-3"
          aria-label="购物车摘要"
        >
          <div className="grid min-w-0 gap-0.5">
            <span className="text-[0.66rem] text-text-muted">商品种类</span>
            <strong className="overflow-wrap-anywhere text-[0.82rem]">{itemCount}</strong>
          </div>
          <div className="grid min-w-0 gap-0.5">
            <span className="text-[0.66rem] text-text-muted">总件数</span>
            <strong className="overflow-wrap-anywhere text-[0.82rem]">{totalQuantity}</strong>
          </div>
          <div className="grid min-w-0 gap-0.5">
            <span className="text-[0.66rem] text-text-muted">当前商品小计</span>
            <strong className="overflow-wrap-anywhere text-[0.82rem]">
              {data.subtotal ? formatMoney(data.subtotal) : "暂不可计算"}
            </strong>
          </div>
          <small className="col-span-3 text-[0.66rem] text-text-muted">按当前商品价格计算</small>
        </div>
      )}
      {mixedCurrency && (
        <p
          className="m-0 rounded-sm bg-warning-soft p-2.5 text-[0.72rem] leading-relaxed text-[#7c4b05]"
          role="status"
        >
          {cartWarningMessage(warnings.find((warning) => warning.code === "mixed_currency")!)}
        </p>
      )}
      {data && items.length === 0 && (
        <p className="m-0 text-[0.72rem] leading-relaxed text-text-muted">购物车还是空的。</p>
      )}
      <div className="grid gap-2.5">
        {items.map((item) => (
          <CartItem
            key={item.cart_item_id}
            item={item}
            warnings={itemWarnings(warnings, item)}
            draftQuantity={draftQuantities[item.cart_item_id] ?? String(item.quantity)}
            busy={
              clearBusy ||
              (updateMutation.isPending &&
                updateMutation.variables?.item.cart_item_id === item.cart_item_id) ||
              (deleteMutation.isPending && deleteMutation.variables === item.cart_item_id)
            }
            error={itemErrors[item.cart_item_id] ?? null}
            onDraftChange={(value) => updateDraft(item.cart_item_id, value)}
            onStep={(delta) => stepDraft(item, delta)}
            onUpdate={() => updateItem(item)}
            onDelete={(trigger) => openDeleteConfirmation(item, trigger)}
          />
        ))}
      </div>
      {data && items.length > 0 && (
        <div className="flex items-center justify-between gap-2.5 border-t border-solid border-border pt-3">
          {onCheckout && (
            <button
              className={cn("cart-checkout-button flex-[1_1_100%]", BUTTON_PRIMARY)}
              disabled={clearBusy || deleteMutation.isPending || updateMutation.isPending}
              onClick={onCheckout}
              type="button"
            >
              去结算
            </button>
          )}
          <button
            className={BUTTON_DANGER}
            disabled={clearBusy || deleteMutation.isPending || updateMutation.isPending}
            onClick={(event) => openClearConfirmation(event.currentTarget)}
            type="button"
          >
            {clearBusy ? "清空中…" : "清空购物车"}
          </button>
          <span className="text-right text-[0.66rem] leading-snug text-text-muted">
            去结算会先生成 Checkout Preview，不会直接创建订单。
          </span>
        </div>
      )}
      {clearError && (
        <p className="m-0 text-[0.72rem] leading-relaxed text-danger" role="alert">
          {clearError}
        </p>
      )}
      {confirmation && (
        <CartConfirmationDialog
          title={confirmation.kind === "delete" ? "移除购物车商品" : "清空购物车"}
          description={
            confirmation.kind === "delete"
              ? `从购物车移除“${confirmation.productName}”？`
              : "确定清空 RetailPilot 购物车吗？"
          }
          confirmLabel={confirmation.kind === "delete" ? "确认移除" : "确认清空"}
          busy={confirmation.kind === "delete" ? deleteMutation.isPending : clearMutation.isPending}
          onCancel={closeConfirmation}
          onConfirm={confirmMutation}
        />
      )}
    </section>
  );
}
