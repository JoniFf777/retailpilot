import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { ApiError } from "../../api/errors";
import { shopMindApi } from "../../api/client";
import type { PaymentAttemptListResponse } from "../../api/contracts";
import { useSession } from "../../app/useSession";
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
  const activePayment = (paymentQuery.data?.items ?? []).find((item) => ["processing", "unknown", "provider_succeeded"].includes(item.status));
  const inconsistentPayment = (paymentQuery.data?.items ?? []).some((item) => item.status === "succeeded" && order?.status === "pending_payment");
  const cancelMutation = useMutation({
    mutationFn: () => shopMindApi.cancelOrder(orderId, backendUserId),
    retry: false,
    onError: (error) => {
      const code = error instanceof ApiError ? error.paymentError?.code ?? error.orderError?.code : null;
      if (code === "payment_in_progress") {
        setCancelMessage("Payment is in progress. Cancel is unavailable until the current Payment Attempt finishes.");
        void Promise.all([
          queryClient.invalidateQueries({ queryKey: paymentAttemptsQueryKey(identity, orderId) }),
          queryClient.invalidateQueries({ queryKey: orderQueryKey(identity, orderId) }),
        ]);
      }
    },
    onSuccess: async (result) => {
      queryClient.setQueryData(orderQueryKey(identity, orderId), result.order);
      await queryClient.invalidateQueries({ queryKey: ordersQueryKey(identity) });
      setCancelMessage(result.idempotent_replay ? "Cancel was already processed." : "Order cancelled. Inventory was released; Cart was not restored.");
    },
  });
  const fromCheckout = Boolean((location.state as { fromCheckout?: boolean } | null)?.fromCheckout);
  const cancelErrorCode = cancelMutation.error instanceof ApiError ? cancelMutation.error.paymentError?.code ?? cancelMutation.error.orderError?.code : null;

  return <section className="order-detail-page" aria-labelledby="order-detail-title">
    <div className="page-heading"><div><p className="eyebrow">ORDER DETAIL</p><h1 id="order-detail-title">Order snapshot</h1></div><div className="page-heading-actions"><Link className="secondary-button" to="/orders">All orders</Link><Link className="secondary-button" to="/">Shopping</Link></div></div>
    {fromCheckout && <div className="success-banner" role="status" data-testid="order-confirmation"><strong>Order created.</strong><span>Your pending-payment order is recorded by ShopMind.</span></div>}
    {query.isLoading && <div className="loading-panel" role="status">Loading order…</div>}
    {query.error && <div className="error-state standalone" role="alert"><div><strong>Order unavailable</strong><p>{query.error instanceof ApiError ? query.error.message : "Try again later."}</p></div><button className="text-button" onClick={() => void query.refetch()} type="button">Retry</button></div>}
    {order && <>
      <section className="order-detail-card" data-testid="order-detail">
        <div className="order-detail-heading"><div><span className="label">Order ID</span><code>{order.order_id}</code></div><OrderStatus status={order.status} /></div>
        <div className="order-facts"><div><span>Status</span><strong>{order.status}</strong></div><div><span>Currency</span><strong>{order.currency}</strong></div><div><span>Version</span><strong>{order.version}</strong></div><div><span>Created</span><strong>{new Date(order.created_at).toLocaleString()}</strong></div>{order.expires_at && <div><span>Payment deadline</span><strong>{new Date(order.expires_at).toLocaleString()}</strong></div>}</div>
        <OrderSnapshot order={order} />
        {order.status === "pending_payment" && <div className="order-cancel-zone"><p>{activePayment ? "Payment is in progress. Cancel is unavailable until the current Payment Attempt finishes." : inconsistentPayment ? "Payment state is inconsistent. Cancel is unavailable until the payment state is reconciled." : "Cancel is explicit. It releases the reservation and does not add items back to Cart."}</p>{!activePayment && !inconsistentPayment && <button className="danger-button" disabled={cancelMutation.isPending} onClick={() => cancelMutation.mutate()} type="button">{cancelMutation.isPending ? "Cancelling…" : "Cancel pending order"}</button>}</div>}
        <PaymentSection order={order} identity={identity} backendUserId={backendUserId} paymentQuery={paymentQuery} />
        {cancelMessage && <p className="success-copy" role="status">{cancelMessage}</p>}
        {cancelMutation.error && cancelErrorCode !== "payment_in_progress" && <p className="error-copy" role="alert">{cancelMutation.error instanceof ApiError ? cancelMutation.error.message : "Cancel failed. Try again."}</p>}
      </section>
    </>}
  </section>;
}
