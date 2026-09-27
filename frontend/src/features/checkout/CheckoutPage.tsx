import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError } from "../../api/errors";
import type { CheckoutPreview, CheckoutWarning, OrderErrorCode } from "../../api/contracts";
import { shopMindApi } from "../../api/client";
import { useSession } from "../../app/useSession";
import { checkoutPreviewQueryKey } from "./checkoutQuery";
import {
  clearCheckoutAttempt,
  newCheckoutAttempt,
  readCheckoutAttempt,
  updateCheckoutAttempt,
  type CheckoutAttempt,
} from "./checkoutAttempt";
import { orderQueryKey, ordersQueryKey } from "../orders/orderQuery";
import { formatMoney } from "../cart/cartFormatters";
import { cartQueryKey } from "../cart/cartQuery";

const REPREVIEW_CODES = new Set<OrderErrorCode>([
  "cart_changed",
  "price_changed",
  "checkout_expired",
  "checkout_invalid",
  "mixed_currency",
  "product_inactive",
  "sku_inactive",
  "inventory_missing",
  "insufficient_inventory",
]);

function errorCode(error: unknown): OrderErrorCode | null {
  if (!(error instanceof ApiError)) return null;
  return error.orderError?.code ?? error.checkoutError?.code ?? null;
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.orderError?.code === "checkout_unavailable")
      return "Checkout service is temporarily unavailable. You can retry this submission.";
    if (error.orderError?.code === "idempotency_conflict")
      return "This submission key was already used for a different request. Start a new Preview before trying again.";
    return error.orderError?.message ?? error.checkoutError?.message ?? error.message;
  }
  return "提交结果未知，可以用同一个 checkout attempt 重试。";
}

function warningLabel(warning: CheckoutWarning): string {
  return warning.message || warning.code.replaceAll("_", " ");
}

function PreviewItem({ item }: { item: NonNullable<CheckoutPreview["items"]>[number] }) {
  return (
    <article className="checkout-item" data-testid="checkout-item">
      <div>
        <strong>{item.product_name}</strong>
        <span>{item.sku_name}</span>
        <small>SKU {item.sku_id}</small>
      </div>
      <div className="checkout-item-numbers">
        <span>数量 {item.quantity}</span>
        <span>单价 {formatMoney(item.unit_money)}</span>
        <strong>{formatMoney(item.subtotal_money)}</strong>
      </div>
    </article>
  );
}

export function CheckoutPage() {
  const { isDevelopment, userId } = useSession();
  const identity = isDevelopment ? userId.trim() : "trusted";
  const backendUserId = isDevelopment ? identity : undefined;
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const previewDataRef = useRef<CheckoutPreview | undefined>(undefined);
  const submittingAttemptIdRef = useRef<string | null>(null);
  const previousIdentityRef = useRef(identity);
  const [attempt, setAttempt] = useState<CheckoutAttempt | null>(() => {
    const saved = readCheckoutAttempt(identity);
    return saved?.submissionState === "unknown" ? saved : null;
  });
  const [needsRepreview, setNeedsRepreview] = useState(false);
  const [submissionError, setSubmissionError] = useState<string | null>(null);

  const previewQuery = useQuery({
    queryKey: checkoutPreviewQueryKey(identity),
    queryFn: ({ signal }) => shopMindApi.checkoutPreview(backendUserId, signal),
    enabled: Boolean(identity) && !attempt,
    staleTime: 0,
    gcTime: 0,
    retry: false,
    refetchOnMount: "always",
  });

  useEffect(() => {
    if (previousIdentityRef.current === identity) return;
    const previousIdentity = previousIdentityRef.current;
    previousIdentityRef.current = identity;
    submittingAttemptIdRef.current = null;
    previewDataRef.current = undefined;
    queryClient.removeQueries({ queryKey: checkoutPreviewQueryKey(previousIdentity) });
    setAttempt(null);
    setSubmissionError(null);
    setNeedsRepreview(false);
  }, [identity, queryClient]);

  useEffect(() => {
    if (!previewQuery.data || previewDataRef.current === previewQuery.data) return;
    previewDataRef.current = previewQuery.data;
    if (attempt) return;
    clearCheckoutAttempt(identity);
    setAttempt(null);
  }, [attempt, identity, previewQuery.data]);

  const orderMutation = useMutation({
    mutationFn: ({ currentAttempt }: { currentAttempt: CheckoutAttempt }) =>
      shopMindApi.createOrder(
        { checkout_token: currentAttempt.checkoutToken },
        currentAttempt.idempotencyKey,
        backendUserId,
      ),
    retry: false,
    onSuccess: async (result, { currentAttempt }) => {
      updateCheckoutAttempt(currentAttempt, "succeeded");
      submittingAttemptIdRef.current = null;
      clearCheckoutAttempt(identity);
      queryClient.setQueryData(orderQueryKey(identity, result.order.order_id), result.order);
      queryClient.removeQueries({ queryKey: checkoutPreviewQueryKey(identity) });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: cartQueryKey(identity) }),
        queryClient.invalidateQueries({ queryKey: ordersQueryKey(identity) }),
      ]);
      navigate(`/orders/${result.order.order_id}`, { state: { fromCheckout: true } });
    },
    onError: (error, { currentAttempt }) => {
      submittingAttemptIdRef.current = null;
      const code = errorCode(error);
      if (code && REPREVIEW_CODES.has(code)) {
        clearCheckoutAttempt(identity);
        setAttempt(null);
        setNeedsRepreview(true);
      } else if (code === "checkout_unavailable") {
        setAttempt(updateCheckoutAttempt(currentAttempt, "ready"));
      } else if (code === "idempotency_conflict") {
        clearCheckoutAttempt(identity);
        setAttempt(null);
        setNeedsRepreview(true);
      } else {
        setAttempt(updateCheckoutAttempt(currentAttempt, "unknown"));
      }
      setSubmissionError(errorMessage(error));
    },
  });

  function startNewPreview() {
    submittingAttemptIdRef.current = null;
    clearCheckoutAttempt(identity);
    setAttempt(null);
    setNeedsRepreview(false);
    setSubmissionError(null);
    void previewQuery.refetch();
  }

  function submitOrder() {
    if (orderMutation.isPending || submittingAttemptIdRef.current) return;
    const token = previewQuery.data?.checkout_token;
    if (!token && !attempt) return;
    const currentAttempt = attempt ?? newCheckoutAttempt(identity, token ?? "");
    submittingAttemptIdRef.current = currentAttempt.attemptId;
    setAttempt(currentAttempt);
    setSubmissionError(null);
    orderMutation.mutate({ currentAttempt });
  }

  function retryOrder() {
    if (!attempt || orderMutation.isPending || submittingAttemptIdRef.current) return;
    const currentAttempt = updateCheckoutAttempt(attempt, "ready");
    submittingAttemptIdRef.current = currentAttempt.attemptId;
    setAttempt(currentAttempt);
    setSubmissionError(null);
    orderMutation.mutate({ currentAttempt });
  }

  const data = previewQuery.data;
  const items = data?.items ?? [];
  const canCreate = Boolean(data?.can_create_order && data.checkout_token && !needsRepreview);
  const recovering = attempt?.submissionState === "unknown";

  return (
    <section className="checkout-page" aria-labelledby="checkout-title">
      <div className="page-heading">
        <div>
          <p className="eyebrow">CHECKOUT PREVIEW</p>
          <h1 id="checkout-title">确认订单内容</h1>
          <p className="page-lede">创建订单时会重新校验价格和库存。</p>
        </div>
        <Link className="secondary-button" to="/">
          返回购物
        </Link>
      </div>

      {recovering && (
        <section className="checkout-recovery" data-testid="checkout-recovery" role="status">
          <p className="eyebrow">RESULT UNKNOWN</p>
          <h2>没有收到上一次的结果。</h2>
          <p>重试会使用同一个 checkout token 和 Idempotency-Key，不会创建第二个逻辑订单。</p>
          <div className="checkout-actions">
            <button
              className="primary-button"
              disabled={orderMutation.isPending}
              onClick={retryOrder}
              type="button"
            >
              {orderMutation.isPending ? "重试中…" : "Retry submission"}
            </button>
            <button
              className="secondary-button"
              disabled={orderMutation.isPending}
              onClick={startNewPreview}
              type="button"
            >
              重新获取 Preview
            </button>
          </div>
        </section>
      )}

      {!recovering && previewQuery.isLoading && (
        <div className="loading-panel" role="status">
          正在读取最新的购物车 Preview…
        </div>
      )}
      {!recovering && previewQuery.error && (
        <section className="error-state standalone" role="alert">
          <div>
            <strong>Preview 暂时无法读取</strong>
            <p>{errorMessage(previewQuery.error)}</p>
          </div>
          <button className="text-button" onClick={startNewPreview} type="button">
            重新获取 Preview
          </button>
        </section>
      )}
      {!recovering && data && (
        <>
          <section
            className="checkout-preview-card"
            data-testid="checkout-preview"
            aria-labelledby="checkout-preview-title"
          >
            <div className="section-heading">
              <div>
                <p className="eyebrow">SERVER PREVIEW</p>
                <h2 id="checkout-preview-title">订单内容</h2>
              </div>
              <span>
                {data.item_count} 个 SKU · 共 {data.total_quantity} 件
              </span>
            </div>
            {items.length === 0 && (
              <p className="empty-panel">购物车是空的，结算前请先添加商品。</p>
            )}
            <div className="checkout-items">
              {items.map((item) => (
                <PreviewItem item={item} key={item.cart_item_id} />
              ))}
            </div>
            {data.warnings?.length ? (
              <div className="checkout-warnings" role="status">
                <strong>需要留意的提示</strong>
                {data.warnings.map((warning, index) => (
                  <span key={`${warning.code}-${warning.sku_id ?? index}`}>
                    {warningLabel(warning)}
                  </span>
                ))}
              </div>
            ) : null}
            <div className="checkout-total">
              <span>小计</span>
              <strong>{data.subtotal ? formatMoney(data.subtotal) : "暂不可计算"}</strong>
              <small>{data.currency ?? "存在多种币种"}</small>
            </div>
            <p className="checkout-revalidation">
              创建订单时后端会重新核实价格、库存、可售状态、购物车指纹和总额。
            </p>
            {!canCreate && (
              <p className="checkout-blocked" role="alert">
                当前 Preview 已失效，暂时无法创建订单。
              </p>
            )}
            {needsRepreview && (
              <button className="secondary-button" onClick={startNewPreview} type="button">
                Get a new Preview
              </button>
            )}
          </section>
          {canCreate && (
            <section className="checkout-confirm-card" data-testid="checkout-confirm">
              <div>
                <p className="eyebrow">FINAL STEP</p>
                <h2>确认创建订单</h2>
                <p>这是明确的操作，会创建待支付订单。"返回购物"只会离开本页。</p>
              </div>
              <button
                className="primary-button"
                disabled={orderMutation.isPending}
                onClick={submitOrder}
                type="button"
              >
                {orderMutation.isPending ? "创建中…" : "Confirm order"}
              </button>
            </section>
          )}
          {submissionError && (
            <section className="error-state standalone" role="alert">
              <div>
                <strong>订单提交需要处理</strong>
                <p>{submissionError}</p>
              </div>
              {attempt &&
                !needsRepreview &&
                errorCode(orderMutation.error) !== "idempotency_conflict" && (
                  <button
                    className="text-button"
                    disabled={orderMutation.isPending}
                    onClick={retryOrder}
                    type="button"
                  >
                    Retry submission
                  </button>
                )}
            </section>
          )}
        </>
      )}
    </section>
  );
}
