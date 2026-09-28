import type { OrderView } from "../../api/contracts";
import { Badge, type BadgeTone } from "../../components/primitives";
import { LINE_ITEM_ROW } from "../../components/textPatterns";
import { formatMoney } from "../cart/cartFormatters";

export function OrderSnapshot({ order }: { order: OrderView }) {
  return (
    <div className="grid gap-5" data-testid="order-snapshot">
      <div className="grid gap-3">
        {order.items.map((item) => (
          <article className={LINE_ITEM_ROW} key={item.item_id}>
            <div className="grid min-w-0 gap-1">
              <strong className="text-sm">{item.product_name}</strong>
              <span className="text-xs text-text-muted">
                {item.sku_name} · {item.sku_code}
              </span>
              <small className="text-xs text-text-muted">快照 SKU：{item.sku_id}</small>
            </div>
            <div className="grid min-w-40 gap-1 text-right">
              <span className="text-xs text-text-muted">数量 {item.quantity}</span>
              <span className="text-xs text-text-muted">单价 {formatMoney(item.unit_money)}</span>
              <strong className="text-brand-strong">{formatMoney(item.subtotal_money)}</strong>
            </div>
          </article>
        ))}
      </div>
      <div className="grid grid-cols-2 items-center gap-2 border-t border-border pt-4">
        <span className="text-sm text-text-muted">小计</span>
        <strong className="justify-self-end text-sm text-brand-strong">
          {formatMoney(order.subtotal)}
        </strong>
        <span className="text-sm text-text-muted">总计</span>
        <strong className="justify-self-end text-lg text-brand-strong">
          {formatMoney(order.total)}
        </strong>
      </div>
    </div>
  );
}

const STATUS_TONES: Record<OrderView["status"], BadgeTone> = {
  pending_payment: "warning",
  paid: "success",
  expired: "neutral",
  cancelled: "danger",
};

export function OrderStatus({ status }: { status: OrderView["status"] }) {
  const label =
    status === "pending_payment"
      ? "Pending payment"
      : status === "paid"
        ? "Paid"
        : status === "expired"
          ? "Expired"
          : "Cancelled";
  return <Badge tone={STATUS_TONES[status]}>{label}</Badge>;
}
