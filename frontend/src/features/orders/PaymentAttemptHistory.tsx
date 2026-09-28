import type { PaymentAttemptStatus, PaymentAttemptView } from "../../api/contracts";
import { EYEBROW, LOADING_PANEL, SECTION_HEADING } from "../../components/textPatterns";
import { formatMoney } from "../cart/cartFormatters";
import { PAYMENT_STATUS_LABELS } from "./paymentLabels";

const STATUS_TONE: Record<PaymentAttemptStatus, string> = {
  processing: "bg-warning-soft text-warning",
  unknown: "bg-warning-soft text-warning",
  provider_succeeded: "bg-warning-soft text-warning",
  failed: "bg-danger-soft text-danger",
  succeeded: "bg-success-soft text-success",
};

export function PaymentAttemptHistory({ items }: { items: PaymentAttemptView[] }) {
  const validItems = items.filter((item) =>
    Boolean(
      item &&
      typeof item.attempt_id === "string" &&
      typeof item.status === "string" &&
      item.status in PAYMENT_STATUS_LABELS &&
      item.amount &&
      typeof item.amount.amount === "string" &&
      typeof item.amount.currency === "string",
    ),
  );
  return (
    <section
      className="grid gap-3 border-t border-solid border-border pt-4"
      aria-labelledby="payment-history-title"
      data-testid="payment-history"
    >
      <div className={SECTION_HEADING}>
        <div>
          <p className={EYEBROW}>PAYMENT HISTORY</p>
          <h3 className="m-0" id="payment-history-title">
            Payment attempts
          </h3>
        </div>
        <span className="text-xs text-text-subtle">{validItems.length} attempts</span>
      </div>
      {validItems.length === 0 && <p className={LOADING_PANEL}>No Payment Attempt yet.</p>}
      {validItems.length > 0 && (
        <div className="grid gap-2.5">
          {validItems.map((item) => (
            <article
              className="grid gap-2 rounded-sm border border-solid border-[#e0efe9] bg-surface-soft p-3.5"
              data-testid="payment-attempt"
              key={item.attempt_id}
            >
              <div className="flex flex-wrap items-center justify-between gap-2.5">
                <div className="grid gap-1">
                  <strong className="text-sm">{PAYMENT_STATUS_LABELS[item.status]}</strong>
                  <small className="text-xs text-text-subtle">
                    {new Date(item.created_at).toLocaleString()}
                  </small>
                </div>
                <span
                  className={`rounded-full px-2 py-1 text-[0.65rem] font-extrabold ${STATUS_TONE[item.status]}`}
                >
                  {item.status}
                </span>
              </div>
              <div className="flex flex-wrap items-center gap-2.5 text-xs text-text-subtle">
                <span>{formatMoney(item.amount)}</span>
                <span>{item.provider}</span>
                {item.failure_code && <span>{item.failure_code}</span>}
              </div>
              <small className="text-xs text-text-subtle">
                Updated {new Date(item.updated_at).toLocaleString()}
              </small>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
