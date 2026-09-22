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
  return (
    <div className="catalog-state">
      <h2>{title}</h2>
      <p>{detail}</p>
      {action}
    </div>
  );
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
      <section className="catalog-page">
        <CatalogState title="正在打开商品目录" detail="正在读取当前支持的商品类别…" />
      </section>
    );
  if (query.error)
    return (
      <section className="catalog-page">
        <CatalogState title="商品目录暂时不可用" detail={errorMessage(query.error)} />
      </section>
    );
  const categories = query.data?.items ?? [];
  if (categories.length === 0)
    return (
      <section className="catalog-page">
        <CatalogState title="暂无商品类别" detail="当前 Catalog 还没有可浏览的内容。" />
      </section>
    );
  return (
    <section className="catalog-page" aria-labelledby="catalog-title">
      <div className="catalog-heading">
        <div>
          <p className="eyebrow">RETAILPILOT CATALOG</p>
          <h1 id="catalog-title">浏览商品</h1>
          <p className="catalog-lede">从商品类别开始，查看真实库存、价格和结构化规格。</p>
        </div>
        <Link className="secondary-button" to="/">
          返回决策工作台
        </Link>
      </div>
      <div className="catalog-category-grid">
        {categories.map((category) => (
          <Link
            className="catalog-category-card"
            key={category.code}
            to={`/catalog/${encodeURIComponent(category.code)}`}
          >
            <span className="catalog-card-kicker">{category.code}</span>
            <h2>{category.display_name}</h2>
            <p>
              {category.product_count} 个商品 · {category.available_product_count} 个有货
            </p>
            <span className="catalog-card-link">查看商品 →</span>
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
    <div className="catalog-sku-actions">
      <button
        className="primary-button"
        disabled={!sku.availability.in_stock || busy}
        onClick={() => prepare.mutate()}
        type="button"
      >
        {prepare.isPending ? "准备中…" : sku.availability.in_stock ? "加入购物车" : "暂时缺货"}
      </button>
      {messageError && !action && (
        <p className="catalog-inline-error" role="alert">
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
    <article className="catalog-product-card">
      <div className="catalog-product-card-heading">
        <div>
          <span className="catalog-card-kicker">
            {product.brand} · {product.product_code}
          </span>
          <h2>{product.name}</h2>
        </div>
        <strong>{product.skus[0] ? money(product.skus[0].money) : "—"}</strong>
      </div>
      <CatalogSpecifications specifications={product.specifications ?? []} compact />
      <div className="catalog-product-card-meta">
        {product.skus.map((sku) => (
          <span key={sku.sku_id}>
            {sku.sku_name} · {availability(sku)}
          </span>
        ))}
      </div>
      <div className="catalog-product-card-actions">
        <Link
          className="secondary-button"
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
      <section className="catalog-page">
        <CatalogState title="正在读取商品" detail="正在读取该类别的商品和库存…" />
      </section>
    );
  if (query.error)
    return (
      <section className="catalog-page">
        <CatalogState
          title="无法打开该类别"
          detail={errorMessage(query.error)}
          action={
            <Link className="secondary-button" to="/catalog">
              返回全部类别
            </Link>
          }
        />
      </section>
    );
  const data = query.data;
  const items = data?.items ?? [];
  if (!data || items.length === 0)
    return (
      <section className="catalog-page">
        <CatalogState
          title="这个类别暂无商品"
          detail="可以返回全部类别浏览其他商品。"
          action={
            <Link className="secondary-button" to="/catalog">
              返回全部类别
            </Link>
          }
        />
      </section>
    );
  return (
    <section className="catalog-page" aria-labelledby="catalog-category-title">
      <div className="catalog-heading">
        <div>
          <Link className="catalog-back-link" to="/catalog">
            ← 全部类别
          </Link>
          <p className="eyebrow">{data.category.code}</p>
          <h1 id="catalog-category-title">{data.category.display_name}</h1>
          <p className="catalog-lede">
            {data.total} 个商品 · {data.category.available_product_count} 个有货
          </p>
        </div>
      </div>
      <div className="catalog-product-grid">
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
      <section className="catalog-page">
        <CatalogState title="正在读取商品详情" detail="正在读取价格、库存和规格…" />
      </section>
    );
  if (query.error || !query.data)
    return (
      <section className="catalog-page">
        <CatalogState
          title="商品不存在或暂时不可用"
          detail={errorMessage(query.error)}
          action={
            <button className="secondary-button" onClick={() => navigate(-1)} type="button">
              返回上一页
            </button>
          }
        />
      </section>
    );
  const data = query.data;
  const specifications = data.specifications ?? [];
  return (
    <section className="catalog-page" aria-labelledby="catalog-product-title">
      <div className="catalog-detail-top">
        <Link
          className="catalog-back-link"
          to={`/catalog/${encodeURIComponent(data.category.code)}`}
        >
          ← 返回{data.category.display_name}
        </Link>
        <span className="catalog-card-kicker">
          {data.brand} · {data.product_code}
        </span>
        <h1 id="catalog-product-title">{data.name}</h1>
        <p className="catalog-lede">{data.description ?? "Catalog 商品详情"}</p>
      </div>
      <div className="catalog-detail-layout">
        <section className="catalog-detail-card">
          <div className="section-heading">
            <div>
              <p className="eyebrow">SPECIFICATIONS</p>
              <h2>结构化规格</h2>
            </div>
            <span>{specifications.length} 项</span>
          </div>
          <CatalogSpecifications specifications={specifications} />
        </section>
        <section className="catalog-detail-card">
          <div className="section-heading">
            <div>
              <p className="eyebrow">SKU OPTIONS</p>
              <h2>可选 SKU</h2>
            </div>
            <span>{data.skus.length} 个</span>
          </div>
          <div className="catalog-sku-list">
            {data.skus.map((sku) => (
              <div className="catalog-sku-row" key={sku.sku_id}>
                <div>
                  <strong>{sku.sku_name}</strong>
                  <span>
                    {sku.sku_code} · {money(sku.money)} · {availability(sku)}
                  </span>
                  {(sku.variant_specifications ?? []).length > 0 && (
                    <CatalogSpecifications
                      specifications={sku.variant_specifications ?? []}
                      compact
                    />
                  )}
                </div>
                <CatalogSkuAction sku={sku} />
              </div>
            ))}
          </div>
        </section>
      </div>
    </section>
  );
}
