import type { ActionErrorResponse } from "../../api/contracts";

const messages: Record<ActionErrorResponse["code"], string> = {
  pending_action_not_found: "找不到这项待确认操作。",
  recommendation_not_found: "这条推荐已不可用于创建操作，请重新获取推荐。",
  sku_not_in_recommendation: "该 SKU 不属于这条推荐，请重新选择。",
  invalid_quantity: "数量不合法，请检查输入。",
  invalid_updated_fields: "只能修改服务端声明的字段。",
  version_conflict: "待确认操作已发生变化，正在刷新最新状态。",
  action_resolution_conflict: "该操作已通过另一种方式完成，不能重复执行。",
  action_expired: "这项确认操作已过期，请重新选择商品。",
  catalog_not_found: "商品目录中已找不到该 SKU。",
  catalog_identity_changed: "商品身份已变化，请重新获取推荐。",
  product_inactive: "商品已下架，请重新获取推荐。",
  sku_inactive: "该 SKU 已下架，请重新选择。",
  insufficient_inventory: "当前库存不足，可以减少数量后重试。",
  cart_quantity_limit: "加入后会超过单个 SKU 的数量上限。",
  unsupported_action_schema: "此操作版本不再支持，请重新开始。",
  invalid_action_payload: "待确认操作数据无效，请重新开始。",
};

export function actionErrorMessage(error: ActionErrorResponse): string {
  const details = error.details ?? {};
  if (error.code === "insufficient_inventory" && details.available_quantity !== undefined) return `${messages[error.code]}当前可用 ${details.available_quantity} 件。`;
  if (error.code === "cart_quantity_limit" && details.max_quantity !== undefined) return `${messages[error.code]}上限为 ${details.max_quantity} 件。`;
  return messages[error.code] ?? error.message;
}
