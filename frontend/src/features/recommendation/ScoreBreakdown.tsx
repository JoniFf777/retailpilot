import type { ScoreBreakdownItem } from "../../api/contracts";

export function ScoreBreakdown({ items }: { items: ScoreBreakdownItem[] }) {
  if (items.length === 0) return null;
  return <details className="score-breakdown">
    <summary>查看评分依据</summary>
    <ul>{items.map((item) => <li key={item.code}><span>{item.name}</span><strong>{item.points}/{item.max_points}</strong><small>{item.reason}</small></li>)}</ul>
  </details>;
}
