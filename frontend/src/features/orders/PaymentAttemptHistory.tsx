import type { PaymentAttemptView } from "../../api/contracts";
import { formatMoney } from "../cart/cartFormatters";
import { PAYMENT_STATUS_LABELS } from "./paymentLabels";

export function PaymentAttemptHistory({ items }: { items: PaymentAttemptView[] }) {
  const validItems = items.filter((item) => Boolean(item && typeof item.attempt_id === "string" && typeof item.status === "string" && item.status in PAYMENT_STATUS_LABELS && item.amount && typeof item.amount.amount === "string" && typeof item.amount.currency === "string"));
  return <section className="payment-history" aria-labelledby="payment-history-title" data-testid="payment-history">
    <div className="section-heading"><div><p className="eyebrow">PAYMENT HISTORY</p><h3 id="payment-history-title">Payment attempts</h3></div><span>{validItems.length} attempts</span></div>
    {validItems.length === 0 && <p className="empty-panel">No Payment Attempt yet.</p>}
    {validItems.length > 0 && <div className="payment-history-list">{validItems.map((item) => <article className="payment-history-item" data-testid="payment-attempt" key={item.attempt_id}>
      <div className="payment-history-heading"><div><strong>{PAYMENT_STATUS_LABELS[item.status]}</strong><small>{new Date(item.created_at).toLocaleString()}</small></div><span className={`payment-status payment-status-${item.status}`}>{item.status}</span></div>
      <div className="payment-history-facts"><span>{formatMoney(item.amount)}</span><span>{item.provider}</span>{item.failure_code && <span>{item.failure_code}</span>}</div>
      <small className="payment-history-updated">Updated {new Date(item.updated_at).toLocaleString()}</small>
    </article>)}</div>}
  </section>;
}
