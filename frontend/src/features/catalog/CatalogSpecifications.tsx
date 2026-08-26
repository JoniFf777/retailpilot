import type { CatalogSpecificationView } from "../../api/contracts";

function formatValue(value: CatalogSpecificationView["value"]): string {
  if (Array.isArray(value)) return value.join("、");
  if (typeof value === "boolean") return value ? "是" : "否";
  return String(value);
}

export function CatalogSpecifications({ specifications, compact = false }: { specifications: CatalogSpecificationView[]; compact?: boolean }) {
  const visible = [...specifications].sort((left, right) => left.display_order - right.display_order).slice(0, compact ? 4 : undefined);
  if (visible.length === 0) return <p className="catalog-no-specs">暂无公开规格</p>;
  return <dl className={`catalog-specifications ${compact ? "catalog-specifications-compact" : ""}`}>
    {visible.map((specification) => <div className="catalog-specification" key={specification.key}>
      <dt>{specification.label}</dt>
      <dd>{formatValue(specification.value)}{specification.unit ? ` ${specification.unit}` : ""}</dd>
    </div>)}
  </dl>;
}
