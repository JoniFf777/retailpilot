import type { Recommendation } from "../../api/contracts";
import { cn } from "../../components/cn";
import { BRAND_TAG, BUTTON_PRIMARY, BUTTON_SECONDARY } from "../../components/textPatterns";
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

const AVAILABILITY_TONES: Record<string, string> = {
  available: "bg-success-soft text-success",
  tight: "bg-warning-soft text-warning",
  unavailable: "bg-danger-soft text-danger",
};

const ALT_BUTTON =
  "inline-flex min-h-8 cursor-pointer items-center justify-center whitespace-nowrap rounded-md border border-border bg-surface px-2 text-xs font-semibold text-text-primary disabled:cursor-not-allowed disabled:opacity-50";

export function RecommendationCard({
  item,
  rank,
  inComparison,
  selectedSkuIds,
  onSelectSku,
  onAddToCompare,
  onAddAlternative,
}: Props) {
  const alternatives = item.alternative_skus ?? [];
  return (
    <article
      className="recommendation-card grid gap-3 rounded-lg border border-border bg-surface p-4 shadow-[0_8px_24px_rgb(28,65,55,0.07)]"
      aria-label={`推荐 ${rank}：${item.product_name}`}
    >
      <header className="flex items-start justify-between gap-2.5">
        <span className={BRAND_TAG}>
          推荐 {rank} · {item.category_display_name ?? "推荐商品"}
        </span>
        <span
          className={`rounded-full px-1.5 py-1 text-xs font-bold whitespace-nowrap ${AVAILABILITY_TONES[availabilityTone(item.availability)]}`}
        >
          {formatAvailability(item.availability)}
        </span>
      </header>
      <div className="flex items-start justify-between gap-2.5">
        <div>
          <h3 className="m-0 text-base">{item.product_name}</h3>
          <p className="mt-1 mb-0 text-xs text-text-subtle">{item.sku_name}</p>
        </div>
        <strong className="text-[0.95rem] whitespace-nowrap text-brand-strong">
          {formatMoney(item.money)}
        </strong>
      </div>
      <div className="flex items-baseline justify-between rounded-[0.7rem] bg-surface-soft px-2.5 py-2">
        <span className="text-xs text-text-muted">综合匹配</span>
        <strong className="text-[1.22rem] text-brand-strong">
          {item.score}
          <small className="text-xs text-text-subtle">/100</small>
        </strong>
      </div>
      <p className="m-0 text-sm leading-relaxed text-text-muted">{item.reason}</p>
      <ProductSpecifications
        specifications={item.specifications.length ? item.specifications : undefined}
        comparisonFields={item.comparison_fields}
        compact
      />
      {(item.matched_hard_constraints ?? []).length > 0 && (
        <p className="m-0 text-sm leading-relaxed text-text-muted">
          <strong className="text-text-primary">满足硬约束：</strong>
          {item.matched_hard_constraints?.join("、")}
        </p>
      )}
      {(item.matched_soft_preferences ?? []).length > 0 && (
        <p className="m-0 text-sm leading-relaxed text-text-muted">
          <strong className="text-text-primary">匹配偏好：</strong>
          {item.matched_soft_preferences?.join("、")}
        </p>
      )}
      {(item.soft_tradeoffs ?? []).length > 0 && (
        <p className="m-0 text-sm leading-relaxed text-warning">
          <strong className="text-text-primary">取舍：</strong>
          {item.soft_tradeoffs?.join("、")}
        </p>
      )}
      {alternatives.length > 0 && (
        <div className="grid gap-2.5 border-t border-border pt-3" aria-label="同款其他 SKU">
          <span className="text-xs font-bold text-text-subtle">同款可选 SKU</span>
          {alternatives.map((alternative) => {
            const selected = selectedSkuIds.includes(alternative.sku_id);
            return (
              <div
                className="alternative-item flex items-start justify-between gap-2"
                key={alternative.sku_id}
              >
                <div className="grid min-w-0 gap-0.5">
                  <strong className="text-sm">{alternative.sku_name}</strong>
                  <small className="text-xs text-text-muted">
                    {formatMoney(alternative.money)} ·{" "}
                    {formatAvailability(alternative.availability)}
                  </small>
                  <ProductSpecifications
                    specifications={alternative.differing_specifications ?? []}
                    compact
                  />
                </div>
                <div className="flex flex-wrap items-center justify-end gap-1.5">
                  <button
                    className={ALT_BUTTON}
                    type="button"
                    disabled={!onSelectSku || !alternative.availability.in_stock}
                    onClick={() => onSelectSku?.(alternative.sku_id)}
                  >
                    {alternative.availability.in_stock ? "选择此 SKU" : "暂不可用"}
                  </button>
                  <button
                    className={ALT_BUTTON}
                    type="button"
                    aria-pressed={selected}
                    onClick={() => onAddAlternative(alternativeChoice(item, alternative))}
                  >
                    {selected ? "已加入对比" : "加入对比"}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
      <ScoreBreakdown items={item.score_breakdown} />
      {(item.evidence ?? []).length > 0 && (
        <section
          className="mt-1 rounded-md border border-agent-rag/30 bg-agent-rag/10 p-3"
          aria-label="引用证据"
        >
          <span className="text-xs font-bold text-agent-rag">
            引用证据 · {(item.evidence ?? []).length}
          </span>
          <ul className="m-0 mt-2 grid list-none gap-2 p-0">
            {(item.evidence ?? []).map((evidence, index) => (
              <li
                className="grid gap-0.5"
                key={`${evidence.source}-${evidence.type}-${evidence.field}-${evidence.ref ?? ""}-${index}`}
              >
                <span className="text-[0.67rem] text-text-muted">
                  {evidence.source} · {evidence.type}
                </span>
                <strong className="text-[0.73rem] text-text-muted">{evidence.field}</strong>
                <small className="text-xs text-text-subtle">
                  {evidence.value}
                  {evidence.ref ? `（${evidence.ref}）` : ""}
                </small>
              </li>
            ))}
          </ul>
        </section>
      )}
      <div className="recommendation-card-actions flex flex-wrap gap-2">
        <button
          className={cn("primary-button", BUTTON_PRIMARY)}
          type="button"
          disabled={!onSelectSku || !item.availability.in_stock}
          onClick={() => onSelectSku?.(item.sku_id)}
        >
          {item.availability.in_stock ? "选择此商品" : "暂不可用"}
        </button>
        <button
          className={cn("compare-button", BUTTON_SECONDARY)}
          type="button"
          aria-pressed={inComparison}
          onClick={onAddToCompare}
        >
          {inComparison ? "已加入对比" : "加入对比"}
        </button>
      </div>
    </article>
  );
}
