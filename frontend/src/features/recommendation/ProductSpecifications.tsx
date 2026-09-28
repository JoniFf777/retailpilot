import type { ComparisonField, ProductSpecificationView } from "../../api/contracts";
import { formatSpecificationValue } from "./recommendationFormatters";
import { comparisonFieldToSpecification } from "./recommendationTypes";

export function ProductSpecifications({
  specifications,
  comparisonFields = [],
  compact = false,
  hideLabel = false,
}: {
  specifications?: ProductSpecificationView[];
  comparisonFields?: ComparisonField[];
  compact?: boolean;
  /** Drops the `dt` label and left-aligns the value — for a comparison-table cell
   *  where the row's own `th` already names the field. */
  hideLabel?: boolean;
}) {
  const source = specifications?.length
    ? specifications
    : comparisonFields.map(comparisonFieldToSpecification);
  const visible = [...source]
    .sort((left, right) => left.display_order - right.display_order)
    .slice(0, compact ? 4 : undefined);
  if (visible.length === 0) return null;
  return (
    <dl className="product-specifications m-0 grid min-w-[110px] gap-2">
      {visible.map((specification) => {
        const value = formatSpecificationValue(specification);
        const tags = Array.isArray(value) ? (
          <span className={`flex flex-wrap gap-1 ${hideLabel ? "justify-start" : "justify-end"}`}>
            {value.map((item) => (
              <span className="rounded-full bg-surface-soft px-1.5 py-0.5" key={item}>
                {item}
              </span>
            ))}
          </span>
        ) : (
          value
        );
        if (hideLabel)
          return (
            <div key={specification.code}>
              <dd className="m-0 text-left text-sm text-text-primary">{tags}</dd>
            </div>
          );
        return (
          <div
            key={specification.code}
            className="grid grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)] items-baseline gap-2"
          >
            <dt className="text-xs text-text-subtle">{specification.name}</dt>
            <dd className="m-0 text-right text-sm text-text-primary">{tags}</dd>
          </div>
        );
      })}
    </dl>
  );
}
