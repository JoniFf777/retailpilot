import { useMutation, useQueryClient, type UseQueryResult } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { shopMindApi } from "../../api/client";
import { ApiError } from "../../api/errors";
import type { OrderView, PaymentAttemptListResponse, PaymentAttemptStatus, PaymentErrorCode } from "../../api/contracts";
import { orderQueryKey, ordersQueryKey } from "./orderQuery";
import { paymentAttemptsQueryKey } from "./paymentQuery";
import { PaymentAttemptHistory } from "./PaymentAttemptHistory";
import { PAYMENT_STATUS_LABELS } from "./paymentLabels";
import { clearPaymentSubmission, newPaymentSubmission, readPaymentSubmission, updatePaymentSubmission, type PaymentSubmission, type PaymentSubmissionState } from "./paymentAttempt";

type PaymentQuery = UseQueryResult<PaymentAttemptListResponse, Error>;

const ACTIVE_PAYMENT_STATUSES: PaymentAttemptStatus[] = ["processing", "unknown", "provider_succeeded"];

function paymentCode(error: unknown): PaymentErrorCode | null {
  if (!(error instanceof ApiError)) return null;
  return error.paymentError?.code ?? (error.orderError?.code as PaymentErrorCode | undefined) ?? null;
}

function paymentMessage(error: unknown): string {
  if (error instanceof ApiError) return error.paymentError?.message ?? error.orderError?.message ?? error.message;
  return "The payment result is unknown. Retry with the same Mock Payment request.";
}

function statusForSubmission(submission: PaymentSubmission | null, paymentQuery: PaymentQuery): PaymentAttemptStatus | null {
  const active = paymentQuery.data?.items?.find((item) => ACTIVE_PAYMENT_STATUSES.includes(item.status));
  if (active) return active.status;
  if (submission?.submissionState === "provider_succeeded" || submission?.submissionState === "finalization_pending") return "provider_succeeded";
  if (submission?.submissionState === "unknown") return "unknown";
  if (submission?.submissionState === "processing") return "processing";
  return null;
}

function isRetryableSubmissionState(state: PaymentSubmissionState | undefined): boolean {
  return state === "ready" || state === "unknown" || state === "provider_unavailable" || state === "provider_succeeded" || state === "finalization_pending";
}

export function PaymentSection({ order, identity, backendUserId, paymentQuery }: { order: OrderView; identity: string; backendUserId?: string; paymentQuery: PaymentQuery }) {
  const queryClient = useQueryClient();
  const [submission, setSubmission] = useState<PaymentSubmission | null>(() => readPaymentSubmission(identity, order.order_id));
  const [message, setMessage] = useState<string | null>(null);
  const [conflictDiscarded, setConflictDiscarded] = useState(false);
  const submissionRef = useRef<PaymentSubmission | null>(submission);
  const submittingAttemptIdRef = useRef<string | null>(null);

  useEffect(() => {
    const isPayable = order.status === "pending_payment";
    const saved = isPayable ? readPaymentSubmission(identity, order.order_id) : null;
    if (!isPayable) clearPaymentSubmission(identity, order.order_id);
    submissionRef.current = saved;
    setSubmission(saved);
    setMessage(null);
    setConflictDiscarded(false);
    submittingAttemptIdRef.current = null;
  }, [identity, order.order_id, order.status]);

  const refreshPaymentState = async (includeOrders = false) => {
    const invalidations = [
      queryClient.invalidateQueries({ queryKey: paymentAttemptsQueryKey(identity, order.order_id) }),
      queryClient.invalidateQueries({ queryKey: orderQueryKey(identity, order.order_id) }),
    ];
    if (includeOrders) invalidations.push(queryClient.invalidateQueries({ queryKey: ordersQueryKey(identity) }));
    await Promise.all(invalidations);
  };

  const paymentMutation = useMutation({
    mutationFn: (currentSubmission: PaymentSubmission) => shopMindApi.createPayment(order.order_id, currentSubmission.request, currentSubmission.idempotencyKey, backendUserId),
    retry: false,
    onSuccess: async (result, currentSubmission) => {
      const next = updatePaymentSubmission(currentSubmission, result.payment_attempt.status, result.payment_attempt.attempt_id);
      if (result.payment_attempt.status === "succeeded" || result.order.status === "paid") {
        clearPaymentSubmission(currentSubmission.identity, currentSubmission.orderId);
      }
      const isCurrentView = currentSubmission.identity === identity && currentSubmission.orderId === order.order_id;
      if (!isCurrentView) return;
      submittingAttemptIdRef.current = null;
      submissionRef.current = next;
      if (result.payment_attempt.status === "succeeded" || result.order.status === "paid") {
        submissionRef.current = null;
        setSubmission(null);
      } else {
        setSubmission(next);
      }
      setMessage(null);
      queryClient.setQueryData(orderQueryKey(identity, order.order_id), result.order);
      await refreshPaymentState(result.order.status === "paid");
    },
    onError: async (error, currentSubmission) => {
      const code = paymentCode(error);
      let state: PaymentSubmissionState = "unknown";
      if (code === "payment_declined") state = "failed";
      else if (code === "payment_provider_unavailable") state = "provider_unavailable";
      else if (code === "payment_finalization_pending") state = "finalization_pending";
      else if (code === "idempotency_conflict" || code === "payment_in_progress") {
        clearPaymentSubmission(currentSubmission.identity, currentSubmission.orderId);
      }
      else if (code === "order_already_paid" || code === "order_not_payable" || code === "order_not_found" || code === "order_expired" || code === "payment_state_inconsistent") {
        clearPaymentSubmission(currentSubmission.identity, currentSubmission.orderId);
      } else if (error instanceof ApiError) state = "ready";

      const isDiscardedSubmission = code === "idempotency_conflict" || code === "payment_in_progress" || code === "order_already_paid" || code === "order_not_payable" || code === "order_not_found" || code === "order_expired" || code === "payment_state_inconsistent";
      const isCurrentView = currentSubmission.identity === identity && currentSubmission.orderId === order.order_id;
      if (!isCurrentView) return;
      submittingAttemptIdRef.current = null;
      if (isDiscardedSubmission) {
        submissionRef.current = null;
        setSubmission(null);
      } else if (submissionRef.current) {
        const next = updatePaymentSubmission(currentSubmission, state, currentSubmission.attemptId);
        submissionRef.current = next;
        setSubmission(next);
      }
      if (code === "payment_in_progress") {
        setMessage(paymentMessage(error));
      } else if (code === "idempotency_conflict") {
        setConflictDiscarded(true);
        setMessage(null);
      } else {
        setMessage(paymentMessage(error));
      }
      await refreshPaymentState(code === "order_already_paid");
    },
  });

  function submit(currentSubmission: PaymentSubmission) {
    if (paymentMutation.isPending || submittingAttemptIdRef.current) return;
    submittingAttemptIdRef.current = currentSubmission.idempotencyKey;
    submissionRef.current = currentSubmission;
    setSubmission(currentSubmission);
    setMessage(null);
    paymentMutation.mutate(currentSubmission);
  }

  function startPayment() {
    if (order.status !== "pending_payment" || paymentMutation.isPending || paymentQuery.data?.items.some((item) => ACTIVE_PAYMENT_STATUSES.includes(item.status))) return;
    setConflictDiscarded(false);
    submit(newPaymentSubmission(identity, order.order_id));
  }

  function retryPayment() {
    const current = submissionRef.current;
    if (!current || !isRetryableSubmissionState(current.submissionState)) return;
    submit(updatePaymentSubmission(current, "ready", current.attemptId));
  }

  const items = paymentQuery.data?.items ?? [];
  const activeAttempt = items.find((item) => ACTIVE_PAYMENT_STATUSES.includes(item.status));
  const localState = submission?.submissionState;
  const displayedStatus = statusForSubmission(submission, paymentQuery);
  const canStartNew = order.status === "pending_payment" && !activeAttempt && (localState === undefined || localState === "failed");
  const canRetry = order.status === "pending_payment" && Boolean(submission && isRetryableSubmissionState(localState));
  const providerUnavailable = localState === "provider_unavailable";

  return <section className="payment-section" aria-labelledby="payment-section-title" data-testid="payment-section">
    <div className="section-heading"><div><p className="eyebrow">PAYMENT</p><h2 id="payment-section-title">Mock Payment</h2></div><span>{order.currency} {order.total.amount}</span></div>
    {paymentQuery.isLoading && <div className="loading-panel" role="status">Loading Payment history…</div>}
    {paymentQuery.error && <div className="error-state" role="alert"><p>Payment history unavailable.</p><button className="text-button" onClick={() => void paymentQuery.refetch()} type="button">Retry</button></div>}
    {providerUnavailable && <div className="payment-recovery payment-recovery-known" role="status" data-testid="payment-provider-unavailable"><strong>Payment service temporarily unavailable.</strong><span>Payment history and Order were refreshed. Retry uses the original request.</span>{canRetry && <button className="primary-button" disabled={paymentMutation.isPending} onClick={retryPayment} type="button">{paymentMutation.isPending ? "Retrying…" : "Retry original request"}</button>}</div>}
    {displayedStatus && !providerUnavailable && <div className={`payment-recovery payment-recovery-${displayedStatus}`} role="status" data-testid={`payment-status-${displayedStatus}`}>
      <strong>{PAYMENT_STATUS_LABELS[displayedStatus]}</strong>
      {displayedStatus === "unknown" && <span>可使用原请求继续查询，系统不会创建第二笔支付。</span>}
      {displayedStatus === "provider_succeeded" && <span>本地订单完成处理中。只能继续完成，不能重新支付。</span>}
      {displayedStatus === "processing" && <span>当前 Payment Attempt 仍在处理中。</span>}
      {canRetry && displayedStatus === "unknown" && <button className="primary-button" disabled={paymentMutation.isPending} onClick={retryPayment} type="button">{paymentMutation.isPending ? "查询中…" : "继续查询"}</button>}
      {canRetry && displayedStatus === "provider_succeeded" && <button className="primary-button" disabled={paymentMutation.isPending} onClick={retryPayment} type="button">{paymentMutation.isPending ? "完成中…" : "继续完成"}</button>}
    </div>}
    {conflictDiscarded && <div className="payment-recovery payment-recovery-known" role="alert" data-testid="payment-idempotency-conflict"><strong>Payment request conflict.</strong><span>Automatic retry stopped. Refresh Order and Payment history, then click Mock Payment to start a new attempt.</span><button className="text-button" onClick={() => { setMessage(null); void refreshPaymentState(); }} type="button">Refresh payment state</button></div>}
    {message && !providerUnavailable && <p className="error-copy" role="alert">{message}</p>}
    {order.status === "paid" && <div className="payment-paid" data-testid="payment-paid"><strong>支付成功</strong><span>Order is paid. Payment and Cancel are no longer available.</span></div>}
    {order.status === "cancelled" && <div className="payment-cancelled" data-testid="payment-cancelled">This Order is cancelled and cannot be paid.</div>}
    {order.status === "expired" && <div className="payment-cancelled" data-testid="payment-expired"><strong>Payment deadline expired</strong><span>This Order can still be viewed, but it cannot be paid or cancelled.</span></div>}
    {order.status === "pending_payment" && !paymentQuery.isLoading && !paymentQuery.error && !activeAttempt && !displayedStatus && !providerUnavailable && <div className="payment-action-card">
      {localState === "failed" && <><p>Payment failed. Start a new Mock Payment attempt when you are ready.</p><button className="primary-button" disabled={!canStartNew || paymentMutation.isPending} onClick={startPayment} type="button">再次支付</button></>}
      {localState !== "failed" && <><p>Use the fixed Mock Payment reference. No card or real payment data is collected.</p><button className="primary-button" disabled={!canStartNew || paymentMutation.isPending} onClick={startPayment} type="button">{paymentMutation.isPending ? "支付处理中…" : "Mock Payment"}</button></>}
    </div>}
    {activeAttempt && <div className="payment-in-progress" data-testid="payment-in-progress">Payment is in progress. Cancel is unavailable until the current Attempt finishes.</div>}
    <PaymentAttemptHistory items={items} />
  </section>;
}
