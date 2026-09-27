import type {
  CategoryAttributeConstraint,
  ComparisonField,
  LaptopConstraints,
  Recommendation,
  RecommendationRequest,
} from "../../api/contracts";
import { formatBudget, formatSpecificationValue } from "./recommendationFormatters";

type ConstraintChip = { text: string; role: "hard" | "soft"; key?: string };

function fallbackFields(attributes: Record<string, unknown>): ComparisonField[] {
  return Object.entries(attributes).map(([key, raw], index) => {
    const value =
      raw && typeof raw === "object" && "value" in raw ? (raw as { value: unknown }).value : raw;
    const valueType: ComparisonField["value_type"] = Array.isArray(value)
      ? "string_list"
      : typeof value === "boolean"
        ? "boolean"
        : typeof value === "number"
          ? "number"
          : "string";
    return {
      key,
      label: key,
      value: (valueType === "string_list"
        ? (value as unknown[]).map(String)
        : String(value)) as ComparisonField["value"],
      value_type: valueType,
      display_order: index,
      comparable: false,
    };
  });
}

function fieldValue(field: ComparisonField): string {
  if (field.value_type === "string_list" && Array.isArray(field.value))
    return field.value.join("、");
  if (field.value_type === "boolean") return field.value ? "是" : "否";
  return `${String(field.value)}${field.unit ?? ""}`;
}

function hitRatio(
  fieldKey: string,
  recommendations: Recommendation[] | undefined,
): [number, number] | null {
  if (!recommendations || recommendations.length === 0) return null;
  const matched = recommendations.filter((item) =>
    (item.matched_soft_preferences ?? []).includes(fieldKey),
  ).length;
  return [matched, recommendations.length];
}

function ConstraintList({
  chips,
  recommendations,
}: {
  chips: ConstraintChip[];
  recommendations?: Recommendation[];
}) {
  return (
    <ul>
      {chips.map((chip) => {
        const ratio = chip.role === "soft" && chip.key ? hitRatio(chip.key, recommendations) : null;
        return (
          <li key={chip.text}>
            <span>{chip.text}</span>
            {ratio && (
              <span className="constraint-hit" data-full={ratio[0] === ratio[1] ? "true" : "false"}>
                {ratio[0]}/{ratio[1]} 命中
              </span>
            )}
          </li>
        );
      })}
    </ul>
  );
}

export function StructuredConstraintsPanel({
  constraints,
  recommendationRequest,
  categoryAttributes = {},
  constraintFields = [],
  recognizedConstraints,
  recommendations,
}: {
  constraints: LaptopConstraints;
  recommendationRequest?: RecommendationRequest | null;
  categoryAttributes?: Record<string, unknown>;
  constraintFields?: ComparisonField[];
  recognizedConstraints?: Record<string, CategoryAttributeConstraint>;
  recommendations?: Recommendation[];
}) {
  const fields = constraintFields.length ? constraintFields : fallbackFields(categoryAttributes);
  const budget =
    recommendationRequest?.budget_min != null && recommendationRequest?.budget_max != null
      ? `预算范围：${formatBudget(recommendationRequest.budget_min, recommendationRequest.budget_currency ?? undefined)}～${formatBudget(recommendationRequest.budget_max, recommendationRequest.budget_currency ?? undefined)}`
      : recommendationRequest?.budget_max != null
        ? `预算上限：${formatBudget(recommendationRequest.budget_max, recommendationRequest.budget_currency ?? undefined)}`
        : recommendationRequest?.budget_min != null
          ? `预算下限：${formatBudget(recommendationRequest.budget_min, recommendationRequest.budget_currency ?? undefined)}`
          : null;
  const chips: ConstraintChip[] = [
    ...(budget ? [{ text: budget, role: "hard" as const }] : []),
    ...fields
      .sort(
        (left, right) =>
          left.display_order - right.display_order || left.key.localeCompare(right.key),
      )
      .map((field): ConstraintChip => {
        const raw = categoryAttributes[field.key];
        const polarity =
          raw && typeof raw === "object" && "polarity" in raw
            ? (raw as { polarity?: string }).polarity
            : undefined;
        const text =
          polarity === "exclude"
            ? `${field.label}：不包括${fieldValue(field)}`
            : `${field.label}：${fieldValue(field)}`;
        const role = recognizedConstraints?.[field.key]?.role === "soft" ? "soft" : "hard";
        return { text, role, key: field.key };
      }),
  ];
  if (!chips.length && constraints) {
    const legacy = Object.entries(constraints).filter(
      ([, value]) => value !== null && value !== undefined && value !== "" && !Array.isArray(value),
    );
    chips.push(
      ...legacy.map(
        ([key, value]): ConstraintChip => ({
          text: `${key}：${formatSpecificationValue({ code: key, name: key, value: String(value), value_type: "string", display_order: 0, comparable: false })}`,
          role: "hard",
        }),
      ),
    );
  }
  if (!chips.length) return null;
  const hardChips = chips.filter((chip) => chip.role === "hard");
  const softChips = chips.filter((chip) => chip.role === "soft");
  return (
    <section className="structured-constraints" aria-label="已识别的选购条件">
      <span>已识别条件</span>
      {hardChips.length > 0 && (
        <div className="constraint-group" data-role="hard">
          {softChips.length > 0 && <span className="constraint-group-heading">硬性条件</span>}
          <ConstraintList chips={hardChips} />
        </div>
      )}
      {softChips.length > 0 && (
        <div className="constraint-group" data-role="soft">
          {hardChips.length > 0 && <span className="constraint-group-heading">软性偏好</span>}
          <ConstraintList chips={softChips} recommendations={recommendations} />
        </div>
      )}
    </section>
  );
}
