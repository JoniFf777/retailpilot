import type { OrderView } from "../../api/contracts";
import { formatMoney } from "../cart/cartFormatters";

export function OrderSnapshot({ order }: { order: OrderView }) {
  return <div className="order-snapshot" data-testid="order-snapshot">
    <div className="order-item-list">{order.items.map((item) => <article className="order-item" key={item.item_id}>
      <div><strong>{item.product_name}</strong><span>{item.sku_name} · {item.sku_code}</span><small>Snapshot SKU: {item.sku_id}</small></div>
      <div className="order-item-numbers"><span>Qty {item.quantity}</span><span>{formatMoney(item.unit_money)} each</span><strong>{formatMoney(item.subtotal_money)}</strong></div>
    </article>)}</div>
    <div className="order-total"><span>Subtotal</span><strong>{formatMoney(order.subtotal)}</strong><span>Total</span><strong>{formatMoney(order.total)}</strong></div>
  </div>;
}

export function OrderStatus({ status }: { status: OrderView["status"] }) {
  const label = status === "pending_payment" ? "Pending payment" : status === "paid" ? "Paid" : "Cancelled";
  return <span className={`order-status order-status-${status}`}>{label}</span>;
}
