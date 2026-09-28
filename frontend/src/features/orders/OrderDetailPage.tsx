import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { ApiError } from "../../api/errors";
import { shopMindApi } from "../../api/client";
import type { PaymentAttemptListResponse } from "../../api/contracts";
import { useSession } from "../../app/useSession";
import { Button, Card } from "../../components/primitives";
import {
  BUTTON_SECONDARY,
  ERROR_STATE,
  EYEBROW,
  LOADING_PANEL,
  PAGE_HEADING,
  STAT_CARD,
  TEXT_BUTTON,
} from "../../components/textPatterns";
import { orderQueryKey, ordersQueryKey } from "./orderQuery";
import { paymentAttemptsQueryKey } from "./paymentQuery";
import { PaymentSection } from "./PaymentSection";
import { OrderSnapshot, OrderStatus } from "./OrderSnapshot";

export function OrderDetailPage() {
  const { orderId = "" } = useParams();
  const { isDevelopment, userId } = useSession();
  const identity = isDevelopment ? userId.trim() : "trusted";
  const backendUserId = isDevelopment ? identity : undefined;
  const location = useLocation();
  const queryClient = useQueryClient();
  const [cancelMessage, setCancelMessage] = useState<string | null>(null);
  const query = useQuery({
    queryKey: orderQueryKey(identity, orderId),
    queryFn: ({ signal }) => shopMindApi.getOrder(orderId, backendUserId, signal),
    enabled: Boolean(identity && orderId),
    retry: false,
  });
  const order = query.data;
  const paymentQuery = useQuery<PaymentAttemptListResponse, Error>({
    queryKey: paymentAttemptsQueryKey(identity, orderId),
    queryFn: ({ signal }) => shopMindApi.listPayments(orderId, backendUserId, signal),
    enabled: Boolean(identity && orderId && order),
    retry: false,
  });
  const activePayment = (paymentQuery.data?.items ?? []).find((item) =>
    ["processing", "unknown", "provider_succeeded"].includes(item.status),
  );
  const inconsistentPayment = (paymentQuery.data?.items ?? []).some(
    (item) => item.status === "succeeded" && order?.status === "pending_payment",
  );
  const cancelMutation = useMutation({
    mutationFn: () => shopMindApi.cancelOrder(orderId, backendUserId),
    retry: false,
    onError: (error) => {
      const code =
        error instanceof ApiError ? (error.paymentError?.code ?? error.orderError?.code) : null;
      if (code === "payment_in_progress") {
        setCancelMessage("支付正在进行中，当前 Payment Attempt 完成前无法取消。");
        void Promise.all([
          queryClient.invalidateQueries({ queryKey: paymentAttemptsQueryKey(identity, orderId) }),
          queryClient.invalidateQueries({ queryKey: orderQueryKey(identity, orderId) }),
        ]);
      }
    },
    onSuccess: async (result) => {
      queryClient.setQueryData(orderQueryKey(identity, orderId), result.order);
      await queryClient.invalidateQueries({ queryKey: ordersQueryKey(identity) });
      setCancelMessage(
        result.idempotent_replay
          ? "取消请求此前已处理过。"
          : "Order cancelled. Inventory was released; Cart was not restored.",
      );
    },
  });
  const fromCheckout = Boolean((location.state as { fromCheckout?: boolean } | null)?.fromCheckout);
  const cancelErrorCode =
    cancelMutation.error instanceof ApiError
      ? (cancelMutation.error.paymentError?.code ?? cancelMutation.error.orderError?.code)
      : null;

  return (
    <section className="grid gap-8" aria-labelledby="order-detail-title">
      <div className={PAGE_HEADING}>
        <div>
          <p className={EYEBROW}>ORDER DETAIL</p>
          <h1 id="order-detail-title">订单快照</h1>
        </div>
        <div className="flex flex-wrap gap-2.5">
          <Link className={BUTTON_SECONDARY} to="/orders">
            全部订单
          </Link>
          <Link className={BUTTON_SECONDARY} to="/">
            Shopping
          </Link>
        </div>
      </div>
      {fromCheckout && (
        <div
          className="flex flex-wrap items-center gap-2.5 rounded-lg border border-success/25 bg-success-soft p-4 text-success"
          role="status"
          data-testid="order-confirmation"
        >
          <strong className="text-sm">订单已创建。</strong>
          <span className="text-sm text-text-muted">你的待支付订单已被 RetailPilot 记录。</span>
        </div>
      )}
      {query.isLoading && (
        <div className={LOADING_PANEL} role="status">
          正在读取订单…
        </div>
      )}
      {query.error && (
        <div className={ERROR_STATE} role="alert">
          <div>
            <strong className="text-text-primary">订单暂时无法读取</strong>
            <p className="mt-0.5 text-sm">
              {query.error instanceof ApiError ? query.error.message : "请稍后重试。"}
            </p>
          </div>
          <button className={TEXT_BUTTON} onClick={() => void query.refetch()} type="button">
            重试
          </button>
        </div>
      )}
      {order && (
        <Card as="section" className="grid gap-5" data-testid="order-detail">
          <div className="flex items-center justify-between gap-4 border-b border-border pb-4">
            <div className="grid min-w-0 gap-1">
              <span className="text-xs text-text-muted">Order ID</span>
              <code className="overflow-wrap-anywhere text-brand-strong">{order.order_id}</code>
            </div>
            <OrderStatus status={order.status} />
          </div>
          <div className="grid grid-cols-[repeat(auto-fit,minmax(130px,1fr))] gap-2.5">
            <div className={STAT_CARD}>
              <span className="text-xs text-text-subtle">Status</span>
              <strong className="overflow-wrap-anywhere text-sm">{order.status}</strong>
            </div>
            <div className={STAT_CARD}>
              <span className="text-xs text-text-subtle">币种</span>
              <strong className="overflow-wrap-anywhere text-sm">{order.currency}</strong>
            </div>
            <div className={STAT_CARD}>
              <span className="text-xs text-text-subtle">版本</span>
              <strong className="overflow-wrap-anywhere text-sm">{order.version}</strong>
            </div>
            <div className={STAT_CARD}>
              <span className="text-xs text-text-subtle">创建时间</span>
              <strong className="overflow-wrap-anywhere text-sm">
                {new Date(order.created_at).toLocaleString()}
              </strong>
            </div>
            {order.expires_at && (
              <div className={STAT_CARD}>
                <span className="text-xs text-text-subtle">支付截止时间</span>
                <strong className="overflow-wrap-anywhere text-sm">
                  {new Date(order.expires_at).toLocaleString()}
                </strong>
              </div>
            )}
          </div>
          <OrderSnapshot order={order} />
          {order.status === "pending_payment" && (
            <div className="flex flex-wrap items-center justify-between gap-4 rounded-md border border-danger/25 bg-danger-soft p-4">
              <p className="m-0 max-w-[540px] text-sm leading-relaxed text-danger">
                {activePayment
                  ? "支付正在进行中，当前 Payment Attempt 完成前无法取消。"
                  : inconsistentPayment
                    ? "支付状态不一致，需要先核对支付状态才能取消。"
                    : "取消是明确的操作：会释放库存预留，不会把商品放回购物车。"}
              </p>
              {!activePayment && !inconsistentPayment && (
                <Button
                  disabled={cancelMutation.isPending}
                  onClick={() => cancelMutation.mutate()}
                  type="button"
                  variant="danger"
                >
                  {cancelMutation.isPending ? "取消中…" : "Cancel pending order"}
                </Button>
              )}
            </div>
          )}
          <PaymentSection
            order={order}
            identity={identity}
            backendUserId={backendUserId}
            paymentQuery={paymentQuery}
          />
          {cancelMessage && (
            <p className="m-0 text-sm text-success" role="status">
              {cancelMessage}
            </p>
          )}
          {cancelMutation.error && cancelErrorCode !== "payment_in_progress" && (
            <p className="m-0 text-sm text-danger" role="alert">
              {cancelMutation.error instanceof ApiError
                ? cancelMutation.error.message
                : "取消失败，请重试。"}
            </p>
          )}
        </Card>
      )}
    </section>
  );
}
