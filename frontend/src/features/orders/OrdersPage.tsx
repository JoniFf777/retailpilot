import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ApiError } from "../../api/errors";
import { shopMindApi } from "../../api/client";
import { useSession } from "../../app/useSession";
import { formatMoney } from "../cart/cartFormatters";
import { ordersQueryKey } from "./orderQuery";
import { OrderStatus } from "./OrderSnapshot";

export function OrdersPage() {
  const { isDevelopment, userId } = useSession();
  const identity = isDevelopment ? userId.trim() : "trusted";
  const backendUserId = isDevelopment ? identity : undefined;
  const query = useQuery({
    queryKey: ordersQueryKey(identity),
    queryFn: ({ signal }) => shopMindApi.listOrders(backendUserId, 20, null, signal),
    enabled: Boolean(identity),
    retry: false,
  });
  const orders = query.data?.items ?? [];

  return <section className="orders-page" aria-labelledby="orders-title">
    <div className="page-heading"><div><p className="eyebrow">ORDER HISTORY</p><h1 id="orders-title">Your orders</h1><p className="page-lede">Orders use the backend snapshot: names and prices do not change with live Catalog data.</p></div><Link className="secondary-button" to="/">Back to shopping</Link></div>
    {query.isLoading && <div className="loading-panel" role="status">Loading orders…</div>}
    {query.error && <div className="error-state standalone" role="alert"><div><strong>Orders unavailable</strong><p>{query.error instanceof ApiError ? query.error.message : "Try again later."}</p></div><button className="text-button" onClick={() => void query.refetch()} type="button">Retry</button></div>}
    {query.data && orders.length === 0 && <div className="empty-panel">No orders yet. Add a product to your Cart to begin.</div>}
    {query.data && orders.length > 0 && <div className="order-list" data-testid="order-list">{orders.map((order) => <Link className="order-list-card" key={order.order_id} to={`/orders/${order.order_id}`}>
      <div className="order-list-card-heading"><div><span className="label">Order</span><strong>{order.order_id}</strong></div><OrderStatus status={order.status} /></div>
      <div className="order-list-card-meta"><span>{order.items.length} SKU · {order.currency}</span><strong>{formatMoney(order.total)}</strong></div>
      <small>{new Date(order.created_at).toLocaleString()}</small>
    </Link>)}</div>}
  </section>;
}
