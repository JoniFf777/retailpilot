import type { ScoreBreakdownItem } from "../../api/contracts";

export function ScoreBreakdown({ items }: { items: ScoreBreakdownItem[] }) {
  if (items.length === 0) return null;
  return (
    <details className="border-t border-border pt-3 text-sm text-text-muted">
      <summary className="cursor-pointer font-bold text-brand-strong">查看评分依据</summary>
      <ul className="m-0 mt-2.5 grid list-none gap-2 p-0">
        {items.map((item) => (
          <li className="grid grid-cols-[1fr_auto] gap-0.5" key={item.code}>
            <span>{item.name}</span>
            <strong>
              {item.points}/{item.max_points}
            </strong>
            <small className="col-span-2 text-xs text-text-subtle">{item.reason}</small>
          </li>
        ))}
      </ul>
    </details>
  );
}
