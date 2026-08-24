import type { ComparisonField, LaptopConstraints, RecommendationRequest } from "../../api/contracts";
import { formatBudget, formatSpecificationValue } from "./recommendationFormatters";

function fallbackFields(attributes: Record<string, unknown>): ComparisonField[] {
  return Object.entries(attributes).map(([key, raw], index) => {
    const value = raw && typeof raw === "object" && "value" in raw ? (raw as { value: unknown }).value : raw;
    const valueType: ComparisonField["value_type"] = Array.isArray(value)
      ? "string_list"
      : typeof value === "boolean" ? "boolean" : typeof value === "number" ? "number" : "string";
    return {
      key,
      label: key,
      value: (valueType === "string_list" ? (value as unknown[]).map(String) : String(value)) as ComparisonField["value"],
      value_type: valueType,
      display_order: index,
      comparable: false,
    };
  });
}

function fieldValue(field: ComparisonField): string {
  if (field.value_type === "string_list" && Array.isArray(field.value)) return field.value.join("、");
  if (field.value_type === "boolean") return field.value ? "是" : "否";
  return `${String(field.value)}${field.unit ?? ""}`;
}

export function StructuredConstraintsPanel({
  constraints,
  recommendationRequest,
  categoryAttributes = {},
  constraintFields = [],
}: {
  constraints: LaptopConstraints;
  recommendationRequest?: RecommendationRequest | null;
  categoryAttributes?: Record<string, unknown>;
  constraintFields?: ComparisonField[];
}) {
  const fields = constraintFields.length ? constraintFields : fallbackFields(categoryAttributes);
  const budget = recommendationRequest?.budget_max != null
    ? `预算上限：${formatBudget(recommendationRequest.budget_max, recommendationRequest.budget_currency ?? undefined)}`
    : null;
  const chips = [budget, ...fields.sort((left, right) => left.display_order - right.display_order || left.key.localeCompare(right.key)).map((field) => `${field.label}：${fieldValue(field)}`)].filter((value): value is string => Boolean(value));
  if (!chips.length && constraints) {
    const legacy = Object.entries(constraints).filter(([, value]) => value !== null && value !== undefined && value !== "" && !Array.isArray(value));
    chips.push(...legacy.map(([key, value]) => `${key}：${formatSpecificationValue({ code: key, name: key, value: String(value), value_type: "string", display_order: 0, comparable: false })}`));
  }
  if (!chips.length) return null;
  return <section className="structured-constraints" aria-label="已识别的选购条件"><span>已识别条件</span><ul>{chips.map((chip) => <li key={chip}>{chip}</li>)}</ul></section>;
}
