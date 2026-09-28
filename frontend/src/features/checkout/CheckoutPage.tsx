import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError } from "../../api/errors";
import type { CheckoutPreview, CheckoutWarning, OrderErrorCode } from "../../api/contracts";
import { shopMindApi } from "../../api/client";
import { useSession } from "../../app/useSession";
import { cn } from "../../components/cn";
import { Button, Card } from "../../components/primitives";
import {
  BUTTON_SECONDARY,
  ERROR_STATE,
  EYEBROW,
  LINE_ITEM_ROW,
  LOADING_PANEL,
  PAGE_HEADING,
  PAGE_LEDE,
  SECTION_HEADING,
  TEXT_BUTTON,
} from "../../components/textPatterns";
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
    <article className={LINE_ITEM_ROW} data-testid="checkout-item">
      <div className="grid min-w-0 gap-1">
        <strong className="text-sm">{item.product_name}</strong>
        <span className="text-xs text-text-muted">{item.sku_name}</span>
        <small className="text-xs text-text-muted">SKU {item.sku_id}</small>
      </div>
      <div className="grid min-w-40 gap-1 text-right">
        <span className="text-xs text-text-muted">数量 {item.quantity}</span>
        <span className="text-xs text-text-muted">单价 {formatMoney(item.unit_money)}</span>
        <strong className="text-brand-strong">{formatMoney(item.subtotal_money)}</strong>
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
    <section className="grid gap-8" aria-labelledby="checkout-title">
      <div className={PAGE_HEADING}>
        <div>
          <p className={EYEBROW}>CHECKOUT PREVIEW</p>
          <h1 id="checkout-title">确认订单内容</h1>
          <p className={PAGE_LEDE}>创建订单时会重新校验价格和库存。</p>
        </div>
        <Link className={cn(BUTTON_SECONDARY, "self-start")} to="/">
          返回购物
        </Link>
      </div>

      {recovering && (
        <Card
          as="section"
          className="grid gap-4 border-warning/25 bg-warning-soft"
          data-testid="checkout-recovery"
          role="status"
        >
          <p className={EYEBROW}>RESULT UNKNOWN</p>
          <h2 className="mt-1 text-lg">没有收到上一次的结果。</h2>
          <p className="mt-1.5 text-sm leading-relaxed text-text-muted">
            重试会使用同一个 checkout token 和 Idempotency-Key，不会创建第二个逻辑订单。
          </p>
          <div className="flex flex-wrap gap-2.5">
            <Button disabled={orderMutation.isPending} onClick={retryOrder} type="button">
              {orderMutation.isPending ? "重试中…" : "Retry submission"}
            </Button>
            <Button
              disabled={orderMutation.isPending}
              onClick={startNewPreview}
              type="button"
              variant="secondary"
            >
              重新获取 Preview
            </Button>
          </div>
        </Card>
      )}

      {!recovering && previewQuery.isLoading && (
        <div className={LOADING_PANEL} role="status">
          正在读取最新的购物车 Preview…
        </div>
      )}
      {!recovering && previewQuery.error && (
        <section className={ERROR_STATE} role="alert">
          <div>
            <strong className="text-text-primary">Preview 暂时无法读取</strong>
            <p className="mt-0.5 text-sm">{errorMessage(previewQuery.error)}</p>
          </div>
          <Button onClick={startNewPreview} type="button" variant="ghost">
            重新获取 Preview
          </Button>
        </section>
      )}
      {!recovering && data && (
        <>
          <Card
            as="section"
            className="grid gap-4"
            data-testid="checkout-preview"
            aria-labelledby="checkout-preview-title"
          >
            <div className={SECTION_HEADING}>
              <div>
                <p className={EYEBROW}>SERVER PREVIEW</p>
                <h2 id="checkout-preview-title" className="m-0 text-xl">
                  订单内容
                </h2>
              </div>
              <span className="text-sm text-text-muted">
                {data.item_count} 个 SKU · 共 {data.total_quantity} 件
              </span>
            </div>
            {items.length === 0 && (
              <p className={LOADING_PANEL}>购物车是空的，结算前请先添加商品。</p>
            )}
            <div className="grid gap-3">
              {items.map((item) => (
                <PreviewItem item={item} key={item.cart_item_id} />
              ))}
            </div>
            {data.warnings?.length ? (
              <div
                className="grid gap-1.5 rounded-md border border-warning/25 bg-warning-soft p-4"
                role="status"
              >
                <strong className="text-sm text-warning">需要留意的提示</strong>
                {data.warnings.map((warning, index) => (
                  <span
                    className="text-sm leading-relaxed text-warning"
                    key={`${warning.code}-${warning.sku_id ?? index}`}
                  >
                    {warningLabel(warning)}
                  </span>
                ))}
              </div>
            ) : null}
            <div className="grid grid-cols-[1fr_auto] items-baseline gap-1 border-t border-border pt-4">
              <span className="text-sm text-text-muted">小计</span>
              <strong className="text-[1.35rem] text-brand-strong">
                {data.subtotal ? formatMoney(data.subtotal) : "暂不可计算"}
              </strong>
              <small className="col-start-2 text-right text-sm text-text-muted">
                {data.currency ?? "存在多种币种"}
              </small>
            </div>
            <p className="m-0 rounded-sm border border-brand/25 bg-brand-soft p-3.5 text-sm leading-relaxed text-brand-strong">
              创建订单时后端会重新核实价格、库存、可售状态、购物车指纹和总额。
            </p>
            {!canCreate && (
              <p className="m-0 text-sm text-danger" role="alert">
                当前 Preview 已失效，暂时无法创建订单。
              </p>
            )}
            {needsRepreview && (
              <Button onClick={startNewPreview} type="button" variant="secondary">
                Get a new Preview
              </Button>
            )}
          </Card>
          {canCreate && (
            <Card
              as="section"
              className="grid grid-cols-[1fr_auto] items-center gap-4"
              data-testid="checkout-confirm"
            >
              <div>
                <p className={EYEBROW}>FINAL STEP</p>
                <h2 className="mt-1 text-lg">确认创建订单</h2>
                <p className="mt-1.5 text-sm leading-relaxed text-text-muted">
                  这是明确的操作，会创建待支付订单。“返回购物”只会离开本页。
                </p>
              </div>
              <Button disabled={orderMutation.isPending} onClick={submitOrder} type="button">
                {orderMutation.isPending ? "创建中…" : "Confirm order"}
              </Button>
            </Card>
          )}
          {submissionError && (
            <section className={ERROR_STATE} role="alert">
              <div>
                <strong className="text-text-primary">订单提交需要处理</strong>
                <p className="mt-0.5 text-sm">{submissionError}</p>
              </div>
              {attempt &&
                !needsRepreview &&
                errorCode(orderMutation.error) !== "idempotency_conflict" && (
                  <button
                    className={TEXT_BUTTON}
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
