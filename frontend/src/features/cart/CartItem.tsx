import type { CartItemView, CartWarning } from "../../api/contracts";
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

export function CartItem({ item, warnings, draftQuantity, busy, error, onDraftChange, onStep, onUpdate, onDelete }: CartItemProps) {
  const itemWarnings = warnings.filter((warning) => warning.cart_item_id === item.cart_item_id);
  const unavailable = item.effective_sale_status !== "active"
    || !item.availability.in_stock
    || itemWarnings.some((warning) => isUnavailableWarning(warning.code));
  const validation = validateCartQuantity(draftQuantity);
  const unavailableMessage = itemWarnings.find((warning) => isUnavailableWarning(warning.code));
  const statusMessage = unavailableMessage
    ? cartWarningMessage(unavailableMessage)
    : unavailable
      ? "商品已不可购买，但仍保留在购物车中。"
      : availabilityMessage(item.availability);

  return <article className="shopmind-cart-item">
    <div className="cart-item-heading">
      <div>
        <h3>{item.product_name}</h3>
        <p>{item.sku_name} · {item.sku_code}</p>
      </div>
      <strong>{formatMoney(item.unit_money)} / 件</strong>
    </div>
    <div className="cart-item-meta">
      <span>当前小计：{formatMoney(item.subtotal_money)}</span>
      <span>{item.effective_sale_status === "active" ? "可购买" : "不可购买"}</span>
    </div>
    <div className="cart-item-controls" aria-label={`${item.product_name} 数量和操作`}>
      <div className="quantity-editor">
        <button aria-label="减少数量" disabled={busy || unavailable || !validation.valid || validation.quantity <= MIN_CART_QUANTITY} onClick={() => onStep(-1)} type="button">−</button>
        <label className="sr-only" htmlFor={`cart-quantity-${item.cart_item_id}`}>{item.product_name} 数量</label>
        <input
          aria-label={`${item.product_name} 数量`}
          id={`cart-quantity-${item.cart_item_id}`}
          inputMode="numeric"
          max={MAX_CART_QUANTITY}
          min={MIN_CART_QUANTITY}
          onChange={(event) => onDraftChange(event.target.value)}
          type="text"
          value={draftQuantity}
          disabled={busy || unavailable}
        />
        <button aria-label="增加数量" disabled={busy || unavailable || !validation.valid || validation.quantity >= MAX_CART_QUANTITY} onClick={() => onStep(1)} type="button">＋</button>
        <button className="secondary-button cart-update-button" disabled={busy || unavailable || !validation.valid || validation.quantity === item.quantity} onClick={onUpdate} type="button">{busy ? "更新中…" : "更新"}</button>
      </div>
      <button className="text-button cart-delete-button" disabled={busy} onClick={(event) => onDelete(event.currentTarget)} type="button">删除</button>
    </div>
    {!validation.valid && <p className="cart-validation-error" role="alert">{validation.message}</p>}
    {unavailable && <p className="cart-item-warning" role="status">{statusMessage}</p>}
    {error && <p className="cart-error" role="alert">{error}</p>}
  </article>;
}
