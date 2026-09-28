import type { CatalogSpecificationView } from "../../api/contracts";

function formatValue(value: CatalogSpecificationView["value"]): string {
  if (Array.isArray(value)) return value.join("、");
  if (typeof value === "boolean") return value ? "是" : "否";
  return String(value);
}

export function CatalogSpecifications({
  specifications,
  compact = false,
}: {
  specifications: CatalogSpecificationView[];
  compact?: boolean;
}) {
  const visible = [...specifications]
    .sort((left, right) => left.display_order - right.display_order)
    .slice(0, compact ? 4 : undefined);
  if (visible.length === 0) return <p className="m-0 text-xs text-text-subtle">暂无公开规格</p>;
  return (
    <dl className={`m-0 grid ${compact ? "gap-1.5" : "gap-2"}`}>
      {visible.map((specification) => (
        <div
          className={`flex items-baseline justify-between gap-4 ${compact ? "" : "border-b border-border pb-1.5"}`}
          key={specification.key}
        >
          <dt className="text-[0.74rem] text-text-muted">{specification.label}</dt>
          <dd className="m-0 text-right text-[0.78rem] font-bold">
            {formatValue(specification.value)}
            {specification.unit ? ` ${specification.unit}` : ""}
          </dd>
        </div>
      ))}
    </dl>
  );
}
