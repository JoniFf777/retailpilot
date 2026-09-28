import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ApiError } from "../../api/errors";
import { shopMindApi } from "../../api/client";
import type {
  ActionErrorResponse,
  CatalogProductSummary,
  CatalogSkuView,
  PendingActionTransitionRequest,
  PendingActionView,
} from "../../api/contracts";
import { useSession } from "../../app/useSession";
import { Button, Card, Empty } from "../../components/primitives";
import { EYEBROW, SECTION_HEADING } from "../../components/textPatterns";
import { ActionDrawer } from "../actions/ActionDrawer";
import { cartQueryKey } from "../cart/cartQuery";
import { checkoutPreviewQueryKey } from "../checkout/checkoutQuery";
import { clearCheckoutAttempt } from "../checkout/checkoutAttempt";
import { readOrCreateThreadId } from "../chat/chatStorage";
import {
  catalogCategoriesQueryKey,
  catalogProductQueryKey,
  catalogProductsQueryKey,
} from "./catalogQuery";
import { CatalogSpecifications } from "./CatalogSpecifications";

const CARD_SURFACE =
  "rounded-lg border border-solid border-border bg-surface shadow-soft transition-[border-color,transform] duration-[180ms] ease-standard hover:border-brand hover:-translate-y-0.5";
const KICKER = "text-[0.66rem] font-extrabold tracking-wide text-text-subtle uppercase";
// Link, not <button>, so it can't use the Button primitive (no `as` support there) -
// same visual result as Button variant="secondary" size="md".
const LINK_BUTTON =
  "inline-flex min-h-10 cursor-pointer items-center justify-center gap-2 rounded-md border border-solid border-border-strong bg-surface px-4 text-sm font-semibold text-text-primary transition-colors duration-150 ease-standard hover:bg-surface-soft focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-ring/30";

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return "Catalog 暂时无法读取，请稍后重试。";
}

function money(money: { amount: string; currency: string }): string {
  return `${money.currency} ${money.amount}`;
}

function availability(sku: CatalogSkuView): string {
  return sku.availability.in_stock
    ? `有货 · ${sku.availability.available_quantity} 件`
    : "暂时缺货";
}

function CatalogState({
  title,
  detail,
  action,
}: {
  title: string;
  detail: string;
  action?: ReactNode;
}) {
  return <Empty action={action} description={detail} title={title} />;
}

export function CatalogHomePage() {
  const query = useQuery({
    queryKey: catalogCategoriesQueryKey,
    queryFn: ({ signal }) => shopMindApi.listCatalogCategories(signal),
    staleTime: 30_000,
    retry: false,
  });
  if (query.isLoading)
    return (
      <section className="grid gap-6">
        <CatalogState detail="正在读取当前支持的商品类别…" title="正在打开商品目录" />
      </section>
    );
  if (query.error)
    return (
      <section className="grid gap-6">
        <CatalogState detail={errorMessage(query.error)} title="商品目录暂时不可用" />
      </section>
    );
  const categories = query.data?.items ?? [];
  if (categories.length === 0)
    return (
      <section className="grid gap-6">
        <CatalogState detail="当前 Catalog 还没有可浏览的内容。" title="暂无商品类别" />
      </section>
    );
  return (
    <section aria-labelledby="catalog-title" className="grid gap-6">
      <div className="grid grid-cols-[minmax(0,1fr)_auto] items-end gap-2 max-[720px]:grid-cols-1">
        <div>
          <p className={EYEBROW}>RETAILPILOT CATALOG</p>
          <h1 className="m-0" id="catalog-title">
            浏览商品
          </h1>
          <p className="mt-1 text-[0.95rem] leading-relaxed text-text-muted">
            从商品类别开始，查看真实库存、价格和结构化规格。
          </p>
        </div>
        <Link className={`max-[720px]:justify-self-start ${LINK_BUTTON}`} to="/">
          返回决策工作台
        </Link>
      </div>
      <div className="grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-4">
        {categories.map((category) => (
          <Link
            className={`grid min-h-40 gap-2 p-5 ${CARD_SURFACE}`}
            key={category.code}
            to={`/catalog/${encodeURIComponent(category.code)}`}
          >
            <span className={KICKER}>{category.code}</span>
            <h2 className="m-0 text-xl">{category.display_name}</h2>
            <p className="m-0 text-sm text-text-muted">
              {category.product_count} 个商品 · {category.available_product_count} 个有货
            </p>
            <span className="mt-auto text-sm font-extrabold text-brand-strong">查看商品 →</span>
          </Link>
        ))}
      </div>
    </section>
  );
}

function CatalogSkuAction({ sku }: { sku: CatalogSkuView }) {
  const { isDevelopment, userId } = useSession();
  const queryClient = useQueryClient();
  const [action, setAction] = useState<PendingActionView | null>(null);
  const [actionError, setActionError] = useState<ActionErrorResponse | null>(null);
  const [messageError, setMessageError] = useState<string | null>(null);
  const [resolution, setResolution] = useState<{
    requested_quantity?: number | null;
    cart_quantity?: number | null;
    price_changed?: boolean;
    idempotent_replay?: boolean;
  } | null>(null);
  const threadId = readOrCreateThreadId();
  const identity = isDevelopment ? userId.trim() : "trusted";
  const prepare = useMutation({
    mutationFn: () =>
      shopMindApi.createCatalogBrowsePendingAction({
        thread_id: threadId,
        sku_id: sku.sku_id,
        quantity: 1,
        ...(isDevelopment && userId.trim() ? { user_id: userId.trim() } : {}),
      }),
    retry: false,
    onSuccess: (created) => {
      setAction(created);
      setActionError(null);
      setMessageError(null);
      setResolution(null);
    },
    onError: (error) => {
      setActionError(error instanceof ApiError ? error.actionError : null);
      setMessageError(errorMessage(error));
    },
  });
  const transition = useMutation({
    mutationFn: ({
      confirmed,
      fields,
    }: {
      confirmed: boolean;
      fields?: PendingActionTransitionRequest["updated_fields"];
    }) => {
      if (!action) throw new Error("No pending catalog action");
      if (confirmed)
        return shopMindApi.confirmPendingAction(action.pending_action_id, {
          thread_id: threadId,
          expected_version: action.version,
          ...(isDevelopment && userId.trim() ? { user_id: userId.trim() } : {}),
          ...(fields ? { updated_fields: fields } : {}),
        });
      return shopMindApi.cancelPendingAction(action.pending_action_id, {
        thread_id: threadId,
        expected_version: action.version,
        ...(isDevelopment && userId.trim() ? { user_id: userId.trim() } : {}),
      });
    },
    retry: false,
    onSuccess: async (result, variables) => {
      setAction(result.pending_action);
      setResolution(result);
      setActionError(null);
      setMessageError(null);
      if (variables.confirmed && result.cart_item) {
        clearCheckoutAttempt(identity);
        queryClient.removeQueries({ queryKey: checkoutPreviewQueryKey(identity) });
        await queryClient.invalidateQueries({ queryKey: cartQueryKey(identity) });
      }
    },
    onError: (error) => {
      setActionError(error instanceof ApiError ? error.actionError : null);
      setMessageError(errorMessage(error));
    },
  });
  const busy = prepare.isPending || transition.isPending;
  return (
    <div className="grid justify-items-start gap-2">
      <Button disabled={!sku.availability.in_stock || busy} onClick={() => prepare.mutate()}>
        {prepare.isPending ? "准备中…" : sku.availability.in_stock ? "加入购物车" : "暂时缺货"}
      </Button>
      {messageError && !action && (
        <p className="m-0 text-xs text-danger" role="alert">
          {messageError}
        </p>
      )}
      {action && (
        <ActionDrawer
          action={action}
          busy={busy}
          error={actionError}
          resolution={resolution}
          onCancel={() => transition.mutate({ confirmed: false })}
          onConfirm={(fields) => transition.mutate({ confirmed: true, fields })}
          onDismiss={() => setAction(null)}
        />
      )}
    </div>
  );
}

function CatalogProductCard({ product }: { product: CatalogProductSummary }) {
  return (
    <article className={`catalog-product-card grid gap-4 p-4.5 ${CARD_SURFACE}`}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <span className={KICKER}>
            {product.brand} · {product.product_code}
          </span>
          <h2 className="mt-1 mb-0 text-lg">{product.name}</h2>
        </div>
        <strong className="text-[0.88rem] whitespace-nowrap text-brand-strong">
          {product.skus[0] ? money(product.skus[0].money) : "—"}
        </strong>
      </div>
      <CatalogSpecifications compact specifications={product.specifications ?? []} />
      <div className="grid gap-1 text-xs text-text-muted">
        {product.skus.map((sku) => (
          <span key={sku.sku_id}>
            {sku.sku_name} · {availability(sku)}
          </span>
        ))}
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2.5 border-t border-solid border-border pt-3">
        <Link
          className={LINK_BUTTON}
          to={`/catalog/${encodeURIComponent(product.category.code)}/${encodeURIComponent(product.product_code)}`}
        >
          查看详情
        </Link>
        {product.skus[0] && <CatalogSkuAction sku={product.skus[0]} />}
      </div>
    </article>
  );
}

export function CatalogCategoryPage() {
  const { category = "" } = useParams();
  const query = useQuery({
    queryKey: catalogProductsQueryKey(category),
    queryFn: ({ signal }) => shopMindApi.listCatalogProducts(category, 100, 0, signal),
    enabled: Boolean(category),
    retry: false,
  });
  if (query.isLoading)
    return (
      <section className="grid gap-6">
        <CatalogState detail="正在读取该类别的商品和库存…" title="正在读取商品" />
      </section>
    );
  if (query.error)
    return (
      <section className="grid gap-6">
        <CatalogState
          action={
            <Link className={LINK_BUTTON} to="/catalog">
              返回全部类别
            </Link>
          }
          detail={errorMessage(query.error)}
          title="无法打开该类别"
        />
      </section>
    );
  const data = query.data;
  const items = data?.items ?? [];
  if (!data || items.length === 0)
    return (
      <section className="grid gap-6">
        <CatalogState
          action={
            <Link className={LINK_BUTTON} to="/catalog">
              返回全部类别
            </Link>
          }
          detail="可以返回全部类别浏览其他商品。"
          title="这个类别暂无商品"
        />
      </section>
    );
  return (
    <section aria-labelledby="catalog-category-title" className="grid gap-6">
      <div className="grid grid-cols-[minmax(0,1fr)_auto] items-end gap-2 max-[720px]:grid-cols-1">
        <div>
          <Link className="text-sm font-extrabold text-brand-strong" to="/catalog">
            ← 全部类别
          </Link>
          <p className={EYEBROW}>{data.category.code}</p>
          <h1 className="m-0" id="catalog-category-title">
            {data.category.display_name}
          </h1>
          <p className="mt-1 text-[0.95rem] leading-relaxed text-text-muted">
            {data.total} 个商品 · {data.category.available_product_count} 个有货
          </p>
        </div>
      </div>
      <div className="grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-4">
        {items.map((product) => (
          <CatalogProductCard key={product.product_id} product={product} />
        ))}
      </div>
    </section>
  );
}

export function CatalogProductDetailPage() {
  const { product = "" } = useParams();
  const navigate = useNavigate();
  const query = useQuery({
    queryKey: catalogProductQueryKey(product),
    queryFn: ({ signal }) => shopMindApi.getCatalogProduct(product, signal),
    enabled: Boolean(product),
    retry: false,
  });
  if (query.isLoading)
    return (
      <section className="grid gap-6">
        <CatalogState detail="正在读取价格、库存和规格…" title="正在读取商品详情" />
      </section>
    );
  if (query.error || !query.data)
    return (
      <section className="grid gap-6">
        <CatalogState
          action={
            <Button onClick={() => navigate(-1)} variant="secondary">
              返回上一页
            </Button>
          }
          detail={errorMessage(query.error)}
          title="商品不存在或暂时不可用"
        />
      </section>
    );
  const data = query.data;
  const specifications = data.specifications ?? [];
  return (
    <section aria-labelledby="catalog-product-title" className="grid gap-6">
      <div className="grid gap-2">
        <Link
          className="text-sm font-extrabold text-brand-strong"
          to={`/catalog/${encodeURIComponent(data.category.code)}`}
        >
          ← 返回{data.category.display_name}
        </Link>
        <span className={KICKER}>
          {data.brand} · {data.product_code}
        </span>
        <h1 className="m-0" id="catalog-product-title">
          {data.name}
        </h1>
        <p className="mt-1 text-[0.95rem] leading-relaxed text-text-muted">
          {data.description ?? "Catalog 商品详情"}
        </p>
      </div>
      <div className="grid grid-cols-2 gap-4 max-[720px]:grid-cols-1">
        <Card className="grid gap-4">
          <div className={SECTION_HEADING}>
            <div>
              <p className={EYEBROW}>SPECIFICATIONS</p>
              <h2>结构化规格</h2>
            </div>
            <span className="text-xs text-text-subtle">{specifications.length} 项</span>
          </div>
          <CatalogSpecifications specifications={specifications} />
        </Card>
        <Card className="grid gap-4">
          <div className={SECTION_HEADING}>
            <div>
              <p className={EYEBROW}>SKU OPTIONS</p>
              <h2>可选 SKU</h2>
            </div>
            <span className="text-xs text-text-subtle">{data.skus.length} 个</span>
          </div>
          <div className="grid gap-3">
            {data.skus.map((sku) => (
              <div
                className="flex items-start justify-between gap-3 border-t border-solid border-border pt-3 first:border-t-0 first:pt-0 max-[720px]:flex-col"
                key={sku.sku_id}
              >
                <div className="grid min-w-0 gap-1">
                  <strong className="text-[0.82rem]">{sku.sku_name}</strong>
                  <span className="overflow-wrap-anywhere text-xs text-text-muted">
                    {sku.sku_code} · {money(sku.money)} · {availability(sku)}
                  </span>
                  {(sku.variant_specifications ?? []).length > 0 && (
                    <CatalogSpecifications
                      compact
                      specifications={sku.variant_specifications ?? []}
                    />
                  )}
                </div>
                <CatalogSkuAction sku={sku} />
              </div>
            ))}
          </div>
        </Card>
      </div>
    </section>
  );
}
