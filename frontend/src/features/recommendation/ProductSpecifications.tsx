import type { ComparisonField, ProductSpecificationView } from "../../api/contracts";
import { formatSpecificationValue } from "./recommendationFormatters";
import { comparisonFieldToSpecification } from "./recommendationTypes";

export function ProductSpecifications({
  specifications,
  comparisonFields = [],
  compact = false,
}: {
  specifications?: ProductSpecificationView[];
  comparisonFields?: ComparisonField[];
  compact?: boolean;
}) {
  const source = specifications?.length
    ? specifications
    : comparisonFields.map(comparisonFieldToSpecification);
  const visible = [...source]
    .sort((left, right) => left.display_order - right.display_order)
    .slice(0, compact ? 4 : undefined);
  if (visible.length === 0) return null;
  return (
    <dl className={`product-specifications ${compact ? "product-specifications-compact" : ""}`}>
      {visible.map((specification) => {
        const value = formatSpecificationValue(specification);
        return (
          <div key={specification.code} className="product-specification">
            <dt>{specification.name}</dt>
            <dd>
              {Array.isArray(value) ? (
                <span className="spec-tags">
                  {value.map((item) => (
                    <span key={item}>{item}</span>
                  ))}
                </span>
              ) : (
                value
              )}
            </dd>
          </div>
        );
      })}
    </dl>
  );
}
