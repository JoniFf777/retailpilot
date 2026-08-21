import type { LaptopConstraints, RecommendationRequest } from "../../api/contracts";
import { formatBudget, formatUseCase } from "./recommendationFormatters";

const fields: Array<[keyof LaptopConstraints, string]> = [
  ["budget_max", "预算上限"], ["memory_min_gb", "内存至少"], ["storage_min_gb", "存储至少"],
  ["weight_max_kg", "重量不超过"], ["cpu_tier_min", "处理器"], ["gpu_tier_min", "显卡"], ["screen_inches", "屏幕"],
];

function valueLabel(key: keyof LaptopConstraints, value: string | number): string {
  if (key === "memory_min_gb" || key === "storage_min_gb") return `${value} GB`;
  if (key === "weight_max_kg") return `${value} kg`;
  if (key === "screen_inches") return `${value} 英寸`;
  return String(value);
}

export function StructuredConstraintsPanel({ constraints, category = "laptop", recommendationRequest, categoryAttributes = {} }: { constraints: LaptopConstraints; category?: string; recommendationRequest?: RecommendationRequest | null; categoryAttributes?: Record<string, unknown> }) {
  const generic = recommendationRequest ?? { budget_max: null, budget_currency: null, generic_preferences: [] };
  const chips = category === "monitor" ? [
    generic.budget_max !== null && generic.budget_max !== undefined ? `预算上限：${formatBudget(generic.budget_max, generic.budget_currency ?? undefined)}` : null,
    typeof categoryAttributes.size_min_inches === "number" || typeof categoryAttributes.size_min_inches === "string" ? `尺寸至少：${categoryAttributes.size_min_inches} 英寸` : null,
    typeof categoryAttributes.resolution_min === "string" ? `分辨率至少：${categoryAttributes.resolution_min}` : null,
    typeof categoryAttributes.refresh_rate_min_hz === "number" ? `刷新率至少：${categoryAttributes.refresh_rate_min_hz} Hz` : null,
    typeof categoryAttributes.panel_type === "string" ? `面板：${categoryAttributes.panel_type.toUpperCase()}` : null,
    typeof categoryAttributes.use_case === "string" ? `用途：${categoryAttributes.use_case}` : null,
  ].filter((value): value is string => Boolean(value)) : fields.flatMap(([key, label]) => {
    const value = constraints[key];
    return value === null || value === undefined || value === "" || Array.isArray(value) || key === "budget_currency" ? [] : [`${label}：${key === "budget_max" ? formatBudget(value, constraints.budget_currency) : valueLabel(key, value)}`];
  });
  const useCases = category === "monitor" ? [] : [...(constraints.primary_use_cases ?? []), ...(constraints.secondary_use_cases ?? [])].filter(Boolean).map(formatUseCase);
  if (useCases.length) chips.push(`用途：${useCases.join("、")}`);
  if (!chips.length) return null;
  return <section className="structured-constraints" aria-label="已识别的选购条件"><span>已识别条件</span><ul>{chips.map((chip) => <li key={chip}>{chip}</li>)}</ul></section>;
}
