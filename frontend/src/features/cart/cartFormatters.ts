import type { AvailabilityView, Money } from "../../api/contracts";

export function formatMoney(money: Money): string { return `${money.currency} ${money.amount}`; }
export function availabilityMessage(availability: AvailabilityView): string {
  if (availability.reason_code === "inventory_missing") return "库存信息暂不可用";
  if (availability.reason_code === "out_of_stock") return "当前无库存";
  if (availability.sale_status !== "active") return "商品状态已变化";
  return availability.in_stock ? `可用 ${availability.available_quantity} 件` : "当前不可用";
}
