import type {
  AlternativeSkuView,
  ComparisonField,
  ProductSpecificationView,
  Recommendation,
  RecommendationResult,
} from "../../api/contracts";

export type RecommendationChoice = Pick<
  Recommendation,
  "sku_id" | "sku_name" | "product_name" | "money" | "availability" | "specifications"
> & { score?: number };
export type AlternativeChoice = RecommendationChoice & {
  differing_specifications: ProductSpecificationView[];
};

export function mainChoice(item: Recommendation): RecommendationChoice {
  return {
    ...item,
    specifications: item.specifications.length
      ? item.specifications
      : (item.comparison_fields ?? []).map(comparisonFieldToSpecification),
  };
}

export function comparisonFieldToSpecification(field: ComparisonField): ProductSpecificationView {
  const valueType =
    field.value_type === "number"
      ? typeof field.value === "number"
        ? "integer"
        : "decimal"
      : field.value_type === "enum"
        ? "string"
        : field.value_type;
  return {
    code: field.key,
    name: field.label,
    value: field.value,
    value_type: valueType,
    unit: field.unit,
    display_order: field.display_order,
    comparable: field.comparable,
  };
}

export function alternativeChoice(
  item: Recommendation,
  alternative: AlternativeSkuView,
): AlternativeChoice {
  const differingSpecifications = alternative.differing_specifications ?? [];
  const differingCodes = new Set(
    differingSpecifications.map((specification) => specification.code),
  );
  const baseSpecifications = item.specifications.length
    ? item.specifications
    : (item.comparison_fields ?? []).map(comparisonFieldToSpecification);
  const specifications = [
    ...baseSpecifications.filter((specification) => !differingCodes.has(specification.code)),
    ...differingSpecifications,
  ].sort(
    (left, right) =>
      left.display_order - right.display_order || left.code.localeCompare(right.code),
  );
  return {
    sku_id: alternative.sku_id,
    sku_name: alternative.sku_name,
    product_name: item.product_name,
    money: alternative.money,
    availability: alternative.availability,
    specifications,
    differing_specifications: differingSpecifications,
  };
}

export function comparableSpecifications(
  specifications: ProductSpecificationView[],
): ProductSpecificationView[] {
  return specifications.filter((specification) => specification.comparable);
}

export function recommendationsOf(result: RecommendationResult): Recommendation[] {
  return (result.recommendations ?? []).slice(0, 3);
}
