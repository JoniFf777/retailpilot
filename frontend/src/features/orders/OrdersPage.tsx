import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ApiError } from "../../api/errors";
import { shopMindApi } from "../../api/client";
import { useSession } from "../../app/useSession";
import { cn } from "../../components/cn";
import { Empty } from "../../components/primitives";
import {
  BUTTON_SECONDARY,
  ERROR_STATE,
  EYEBROW,
  LOADING_PANEL,
  PAGE_HEADING,
  PAGE_LEDE,
  TEXT_BUTTON,
} from "../../components/textPatterns";
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

  return (
    <section className="grid gap-8" aria-labelledby="orders-title">
      <div className={PAGE_HEADING}>
        <div>
          <p className={EYEBROW}>ORDER HISTORY</p>
          <h1 id="orders-title">我的订单</h1>
          <p className={PAGE_LEDE}>订单使用后端快照：名称和价格不会随目录实时数据变化。</p>
        </div>
        <Link className={cn(BUTTON_SECONDARY, "self-start")} to="/">
          返回购物
        </Link>
      </div>
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
      {query.data && orders.length === 0 && (
        <Empty title="还没有订单" description="先去购物车加一件商品开始。" />
      )}
      {query.data && orders.length > 0 && (
        <div className="grid gap-3" data-testid="order-list">
          {orders.map((order) => (
            <Link
              className="grid gap-3 rounded-md border border-border bg-surface/92 p-4 text-inherit no-underline shadow-soft transition-[border-color,transform,box-shadow] duration-150 ease-standard hover:-translate-y-0.5 hover:border-brand hover:shadow-md"
              key={order.order_id}
              to={`/orders/${order.order_id}`}
            >
              <div className="flex items-center justify-between gap-4">
                <div className="grid min-w-0 gap-0.5">
                  <span className="text-xs text-text-muted">订单</span>
                  <strong className="overflow-hidden text-sm text-ellipsis">
                    {order.order_id}
                  </strong>
                </div>
                <OrderStatus status={order.status} />
              </div>
              <div className="flex items-center justify-between gap-4 border-t border-border pt-2.5 text-sm text-text-muted">
                <span>
                  {order.items.length} 个 SKU · {order.currency}
                </span>
                <strong className="text-base text-brand-strong">{formatMoney(order.total)}</strong>
              </div>
              <small className="text-xs text-text-subtle">
                {new Date(order.created_at).toLocaleString()}
              </small>
            </Link>
          ))}
        </div>
      )}
    </section>
  );
}
