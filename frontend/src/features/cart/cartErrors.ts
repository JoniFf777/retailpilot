import type { CartErrorResponse, CartWarning, CartWarningCode } from "../../api/contracts";

const CART_ERROR_MESSAGES: Record<CartErrorResponse["code"], string> = {
  cart_item_not_found: "该购物车商品已经不存在，正在刷新购物车。",
  cart_version_conflict: "购物车已在其他操作中更新，已为你刷新最新状态。",
  invalid_quantity: "商品数量无效。",
  cart_quantity_limit: "单个 SKU 最多可加入 20 件。",
  insufficient_inventory: "当前库存不足，请调整数量。",
  product_inactive: "该商品目前已下架，你可以将它从购物车删除。",
  sku_inactive: "当前 SKU 已不可购买，你可以将它从购物车删除。",
  catalog_not_found: "商品信息已发生变化，请删除该购物车项目。",
  inventory_missing: "当前无法确认该 SKU 的库存，请稍后重试或删除该项目。",
};

const CART_WARNING_MESSAGES: Record<CartWarningCode, string> = {
  mixed_currency: "购物车包含不同币种，暂不计算合计。",
  product_inactive: "商品已不可购买，但仍保留在购物车中。",
  sku_inactive: "当前 SKU 已不可购买，但仍保留在购物车中。",
  out_of_stock: "当前商品暂时无库存，但仍保留在购物车中。",
  insufficient_inventory: "当前库存不足，请调整数量。",
  inventory_missing: "当前无法确认该 SKU 的库存。",
};

export function cartErrorMessage(error: CartErrorResponse | null): string {
  return error ? CART_ERROR_MESSAGES[error.code] : "购物车操作失败，请稍后重试。";
}

export function cartWarningMessage(warning: CartWarning): string {
  return CART_WARNING_MESSAGES[warning.code];
}

export function insufficientInventoryMessage(error: CartErrorResponse): string {
  const available = error.details?.available_quantity;
  return typeof available === "number"
    ? `当前库存最多可支持 ${available} 件。`
    : CART_ERROR_MESSAGES.insufficient_inventory;
}

export function isUnavailableWarning(code: CartWarningCode): boolean {
  return ["product_inactive", "sku_inactive", "inventory_missing", "out_of_stock"].includes(code);
}
