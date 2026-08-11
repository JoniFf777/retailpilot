import type { LaptopConstraints } from "../../api/contracts";
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

export function StructuredConstraintsPanel({ constraints }: { constraints: LaptopConstraints }) {
  const chips = fields.flatMap(([key, label]) => {
    const value = constraints[key];
    return value === null || value === undefined || value === "" || Array.isArray(value) || key === "budget_currency" ? [] : [`${label}：${key === "budget_max" ? formatBudget(value, constraints.budget_currency) : valueLabel(key, value)}`];
  });
  const useCases = [...(constraints.primary_use_cases ?? []), ...(constraints.secondary_use_cases ?? [])].filter(Boolean).map(formatUseCase);
  if (useCases.length) chips.push(`用途：${useCases.join("、")}`);
  if (!chips.length) return null;
  return <section className="structured-constraints" aria-label="已识别的选购条件"><span>已识别条件</span><ul>{chips.map((chip) => <li key={chip}>{chip}</li>)}</ul></section>;
}
