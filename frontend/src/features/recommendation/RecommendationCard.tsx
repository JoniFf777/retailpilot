import type { Recommendation } from "../../api/contracts";
import { ProductSpecifications } from "./ProductSpecifications";
import { ScoreBreakdown } from "./ScoreBreakdown";
import { availabilityTone, formatAvailability, formatMoney } from "./recommendationFormatters";
import { alternativeChoice, type AlternativeChoice } from "./recommendationTypes";

type Props = {
  item: Recommendation;
  rank: number;
  inComparison: boolean;
  selectedSkuIds: string[];
  onSelectSku?: (skuId: string) => void;
  onAddToCompare: () => void;
  onAddAlternative: (alternative: AlternativeChoice) => void;
};

export function RecommendationCard({ item, rank, inComparison, selectedSkuIds, onSelectSku, onAddToCompare, onAddAlternative }: Props) {
  const alternatives = item.alternative_skus ?? [];
  return <article className="recommendation-card" aria-label={`推荐 ${rank}：${item.product_name}`}>
    <header><span className="recommendation-rank">推荐 {rank} · {item.category === "monitor" ? "显示器" : "笔记本"}</span><span className={`availability availability-${availabilityTone(item.availability)}`}>{formatAvailability(item.availability)}</span></header>
    <div className="recommendation-title"><div><h3>{item.product_name}</h3><p>{item.sku_name}</p></div><strong className="recommendation-price">{formatMoney(item.money)}</strong></div>
    <div className="recommendation-score"><span>综合匹配</span><strong>{item.score}<small>/100</small></strong></div>
    <p className="recommendation-reason">{item.reason}</p>
    <ProductSpecifications specifications={item.specifications} compact />
    {(item.matched_hard_constraints ?? []).length > 0 && <p className="constraint-copy"><strong>满足硬约束：</strong>{item.matched_hard_constraints?.join("、")}</p>}
    {(item.matched_soft_preferences ?? []).length > 0 && <p className="constraint-copy"><strong>匹配偏好：</strong>{item.matched_soft_preferences?.join("、")}</p>}
    {(item.soft_tradeoffs ?? []).length > 0 && <p className="tradeoff-copy"><strong>取舍：</strong>{item.soft_tradeoffs?.join("、")}</p>}
    {alternatives.length > 0 && <div className="alternative-list" aria-label="同款其他 SKU"><span className="alternative-list-title">同款可选 SKU</span>{alternatives.map((alternative) => { const selected = selectedSkuIds.includes(alternative.sku_id); return <div className="alternative-item" key={alternative.sku_id}><div><strong>{alternative.sku_name}</strong><small>{formatMoney(alternative.money)} · {formatAvailability(alternative.availability)}</small><ProductSpecifications specifications={alternative.differing_specifications ?? []} compact /></div><div className="alternative-actions"><button type="button" disabled={!onSelectSku || !alternative.availability.in_stock} onClick={() => onSelectSku?.(alternative.sku_id)}>{alternative.availability.in_stock ? "选择此 SKU" : "暂不可用"}</button><button type="button" aria-pressed={selected} onClick={() => onAddAlternative(alternativeChoice(item, alternative))}>{selected ? "已加入对比" : "加入对比"}</button></div></div>; })}</div>}
    <ScoreBreakdown items={item.score_breakdown} />
    {(item.evidence ?? []).length > 0 && <details className="evidence-list"><summary>查看证据</summary><ul>{(item.evidence ?? []).map((evidence, index) => <li key={`${evidence.source}-${evidence.type}-${evidence.field}-${evidence.ref ?? ""}-${index}`}><span>{evidence.source} · {evidence.type}</span><strong>{evidence.field}</strong><small>{evidence.value}{evidence.ref ? `（${evidence.ref}）` : ""}</small></li>)}</ul></details>}
    <div className="recommendation-card-actions"><button className="primary-button" type="button" disabled={!onSelectSku || !item.availability.in_stock} onClick={() => onSelectSku?.(item.sku_id)}>{item.availability.in_stock ? "选择此商品" : "暂不可用"}</button><button className="compare-button" type="button" aria-pressed={inComparison} onClick={onAddToCompare}>{inComparison ? "已加入对比" : "加入对比"}</button></div>
  </article>;
}
