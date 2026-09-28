import type { CartItemView, CartWarning } from "../../api/contracts";
import { Card } from "../../components/primitives";
import { availabilityMessage, formatMoney } from "./cartFormatters";
import { cartWarningMessage, isUnavailableWarning } from "./cartErrors";
import { MAX_CART_QUANTITY, MIN_CART_QUANTITY, validateCartQuantity } from "./quantity";

interface CartItemProps {
  item: CartItemView;
  warnings: CartWarning[];
  draftQuantity: string;
  busy: boolean;
  error: string | null;
  onDraftChange: (value: string) => void;
  onStep: (delta: number) => void;
  onUpdate: () => void;
  onDelete: (trigger: HTMLElement) => void;
}

const STEP_BUTTON =
  "inline-flex h-7 w-7 items-center justify-center rounded-md border border-border-strong bg-surface text-base text-text-primary disabled:cursor-not-allowed disabled:opacity-50";

export function CartItem({
  item,
  warnings,
  draftQuantity,
  busy,
  error,
  onDraftChange,
  onStep,
  onUpdate,
  onDelete,
}: CartItemProps) {
  const itemWarnings = warnings.filter((warning) => warning.cart_item_id === item.cart_item_id);
  const unavailable =
    item.effective_sale_status !== "active" ||
    !item.availability.in_stock ||
    itemWarnings.some((warning) => isUnavailableWarning(warning.code));
  const validation = validateCartQuantity(draftQuantity);
  const unavailableMessage = itemWarnings.find((warning) => isUnavailableWarning(warning.code));
  const statusMessage = unavailableMessage
    ? cartWarningMessage(unavailableMessage)
    : unavailable
      ? "商品已不可购买，但仍保留在购物车中。"
      : availabilityMessage(item.availability);

  return (
    <Card as="article" className="shopmind-cart-item grid gap-2.5" padded={false}>
      <div className="cart-item-heading flex items-start justify-between gap-2">
        <div>
          <h3 className="m-0 text-[0.8rem]">{item.product_name}</h3>
          <p className="mt-0.5 mb-0 text-[0.68rem] text-text-muted">
            {item.sku_name} · {item.sku_code}
          </p>
        </div>
        <strong className="text-[0.7rem] whitespace-nowrap text-text-primary">
          {formatMoney(item.unit_money)} / 件
        </strong>
      </div>
      <div className="cart-item-meta flex items-baseline justify-between gap-2 text-[0.7rem] text-text-muted">
        <span>当前小计：{formatMoney(item.subtotal_money)}</span>
        <span>{item.effective_sale_status === "active" ? "可购买" : "不可购买"}</span>
      </div>
      <div
        className="flex items-center justify-between gap-2.5 p-3"
        aria-label={`${item.product_name} 数量和操作`}
      >
        <div className="flex items-center gap-1.5">
          <button
            aria-label="减少数量"
            className={STEP_BUTTON}
            disabled={
              busy || unavailable || !validation.valid || validation.quantity <= MIN_CART_QUANTITY
            }
            onClick={() => onStep(-1)}
            type="button"
          >
            −
          </button>
          <label className="sr-only" htmlFor={`cart-quantity-${item.cart_item_id}`}>
            {item.product_name} 数量
          </label>
          <input
            aria-label={`${item.product_name} 数量`}
            className="h-7 w-12 rounded-md border border-border-strong bg-surface text-center text-[0.78rem] text-text-primary"
            id={`cart-quantity-${item.cart_item_id}`}
            inputMode="numeric"
            max={MAX_CART_QUANTITY}
            min={MIN_CART_QUANTITY}
            onChange={(event) => onDraftChange(event.target.value)}
            type="text"
            value={draftQuantity}
            disabled={busy || unavailable}
          />
          <button
            aria-label="增加数量"
            className={STEP_BUTTON}
            disabled={
              busy || unavailable || !validation.valid || validation.quantity >= MAX_CART_QUANTITY
            }
            onClick={() => onStep(1)}
            type="button"
          >
            ＋
          </button>
          <button
            className="ml-1.5 inline-flex min-h-7 cursor-pointer items-center justify-center rounded-md border border-border-strong bg-brand-soft px-2 text-[0.68rem] font-semibold text-brand-strong disabled:cursor-not-allowed disabled:opacity-50"
            disabled={
              busy || unavailable || !validation.valid || validation.quantity === item.quantity
            }
            onClick={onUpdate}
            type="button"
          >
            {busy ? "更新中…" : "更新"}
          </button>
        </div>
        <button
          className="cursor-pointer rounded-md border-0 bg-transparent p-1 text-[0.7rem] font-semibold text-brand-strong disabled:cursor-not-allowed disabled:opacity-50"
          disabled={busy}
          onClick={(event) => onDelete(event.currentTarget)}
          type="button"
        >
          删除
        </button>
      </div>
      {!validation.valid && (
        <p className="m-0 text-[0.68rem] leading-relaxed text-danger" role="alert">
          {validation.message}
        </p>
      )}
      {unavailable && (
        <p
          className="m-0 rounded-[0.35rem] bg-warning-soft p-2 text-[0.68rem] leading-relaxed text-warning"
          role="status"
        >
          {statusMessage}
        </p>
      )}
      {error && (
        <p className="m-0 text-[0.68rem] leading-relaxed text-danger" role="alert">
          {error}
        </p>
      )}
    </Card>
  );
}
