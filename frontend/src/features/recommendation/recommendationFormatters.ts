import type { AvailabilityView, Money, ProductSpecificationView } from "../../api/contracts";

const USE_CASE_LABELS: Record<string, string> = {
  java_development: "Java 开发",
  software_development: "软件开发",
  video_editing: "视频剪辑",
  travel: "出差携带",
  office: "办公",
};

function groupedAmount(amount: string): string {
  if (!/^\d+(?:\.\d{2})?$/.test(amount)) return amount;
  const [integer, fraction] = amount.split(".");
  return `${integer.replace(/\B(?=(\d{3})+(?!\d))/g, ",")}${fraction === undefined ? "" : `.${fraction}`}`;
}

/** Display-only formatting: the backend's Decimal string is never recalculated. */
export function formatMoney(money: Money): string {
  const amount = groupedAmount(money.amount);
  return money.currency === "CNY" ? `¥${amount}` : `${amount} ${money.currency}`;
}

export function formatBudget(value: string | number, currency?: string | null): string {
  const amount = String(value);
  const normalized = /^\d+(?:\.\d+)?$/.test(amount) ? (() => { const [integer, fraction = ""] = amount.split("."); return `${integer}.${(fraction + "00").slice(0, 2)}`; })() : amount;
  if (currency) return formatMoney({ amount: normalized, currency });
  return groupedAmount(normalized);
}

export function formatUseCase(code: string): string {
  return USE_CASE_LABELS[code] ?? code;
}

export function formatAvailability(availability: AvailabilityView): string {
  if (availability.sale_status !== "active") return "暂不可售";
  if (!availability.in_stock || availability.available_quantity <= 0) return "暂时缺货";
  if (availability.available_quantity <= 3) return "库存紧张";
  return "有货";
}

export function availabilityTone(availability: AvailabilityView): "available" | "tight" | "unavailable" {
  if (availability.sale_status !== "active" || !availability.in_stock || availability.available_quantity <= 0) return "unavailable";
  return availability.available_quantity <= 3 ? "tight" : "available";
}

export function formatSpecificationValue(specification: ProductSpecificationView): string | string[] {
  const { value, value_type: valueType, unit } = specification;
  if (valueType === "string_list" && Array.isArray(value)) return value;
  if (valueType === "boolean" && typeof value === "boolean") return value ? "是" : "否";
  if (valueType === "decimal" && typeof value === "string") return `${value}${unit ?? ""}`;
  if ((valueType === "integer" || valueType === "string") && (typeof value === "number" || typeof value === "string")) return `${value}${unit ?? ""}`;
  return String(value);
}
