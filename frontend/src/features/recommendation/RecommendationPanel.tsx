import { useEffect, useMemo, useRef, useState } from "react";
import type {
  ProjectionError,
  RecommendationContextView,
  RecommendationResult,
} from "../../api/contracts";
import { BRAND_TAG, INFO_BOX } from "../../components/textPatterns";
import { ComparisonDrawer } from "./ComparisonDrawer";
import { RecommendationCard } from "./RecommendationCard";
import { RecommendationOutcomeNotice } from "./RecommendationOutcomeNotice";
import { StructuredConstraintsPanel } from "./StructuredConstraintsPanel";
import { mainChoice, recommendationsOf, type RecommendationChoice } from "./recommendationTypes";

const NOTICE = "grid gap-2 rounded-md border border-warning/25 bg-warning-soft p-4";

export function RecommendationPanel({
  recommendation,
  recommendationContext,
  projectionError,
  onFillPrompt,
  onSelectSku,
}: {
  recommendation?: RecommendationResult | null;
  recommendationContext?: RecommendationContextView | null;
  projectionError?: ProjectionError | null;
  onFillPrompt: (prompt: string) => void;
  onSelectSku?: (skuId: string, context: RecommendationContextView) => void;
}) {
  const [selected, setSelected] = useState<RecommendationChoice[]>([]);
  const [comparisonOpen, setComparisonOpen] = useState(false);
  const [comparisonError, setComparisonError] = useState<string | null>(null);
  const compareTriggerRef = useRef<HTMLButtonElement>(null);
  const recommendations = useMemo(
    () => (recommendation ? recommendationsOf(recommendation) : []),
    [recommendation],
  );
  const resolvedCategory =
    recommendation?.category && recommendation.category !== "unknown"
      ? recommendation.category
      : undefined;
  useEffect(() => {
    setSelected([]);
    setComparisonOpen(false);
    setComparisonError(null);
  }, [recommendation]);
  function toggleChoice(choice: RecommendationChoice) {
    setComparisonError(null);
    setSelected((current) => {
      if (current.some((item) => item.sku_id === choice.sku_id))
        return current.filter((item) => item.sku_id !== choice.sku_id);
      if (current.length >= 4) {
        setComparisonError("最多比较 4 项");
        return current;
      }
      return [...current, choice];
    });
  }
  if (!recommendation && !projectionError) return null;
  return (
    <section
      className="recommendation-panel ml-[3.25rem] grid max-w-[min(100%,900px)] gap-3.5 max-[980px]:ml-0"
      aria-label="结构化推荐结果"
    >
      {projectionError && (
        <div className={NOTICE} role="alert">
          <strong className="text-[0.92rem] text-warning">推荐详情暂时无法显示</strong>
          <p className="m-0 leading-relaxed text-text-muted">
            结构化推荐暂时无法显示，你仍可以查看文字回答或重新发起请求。
          </p>
        </div>
      )}
      {recommendation && (
        <>
          <RecommendationOutcomeNotice result={recommendation} onFillPrompt={onFillPrompt} />
          {resolvedCategory && (
            <StructuredConstraintsPanel
              constraints={recommendation.structured_constraints}
              recommendationRequest={recommendation.recommendation_request}
              categoryAttributes={recommendation.category_attributes ?? {}}
              constraintFields={recommendation.constraint_fields ?? []}
              recognizedConstraints={recommendation.recognized_constraints}
              recommendations={recommendations}
            />
          )}
          {recommendation.evidence_status && recommendation.evidence_status !== "available" && (
            <div className={NOTICE} role="status">
              <strong className="text-[0.92rem] text-warning">
                证据状态：
                {recommendation.evidence_status === "unavailable"
                  ? "文档服务不可用"
                  : recommendation.evidence_status === "degraded"
                    ? "部分通道降级"
                    : "尚未找到支持证据"}
              </strong>
              <p className="m-0 leading-relaxed text-text-muted">
                目录价格与库存仍按结构化数据判断，文档型结论请以引用为准。
              </p>
            </div>
          )}
          {(recommendation.policy_evidence ?? []).length > 0 && (
            <section className={INFO_BOX} aria-label="政策依据">
              <span className={BRAND_TAG}>政策依据</span>
              <ul className="m-0 grid list-none gap-1.5 p-0 text-sm text-text-muted">
                {(recommendation.policy_evidence ?? []).map((item) => (
                  <li key={item.ref ?? `${item.source}-${item.value}`}>
                    {item.section ? `${item.section}：` : ""}
                    {item.value}
                    {item.document_version ? `（版本 ${item.document_version}）` : ""}
                  </li>
                ))}
              </ul>
            </section>
          )}
          {recommendation.outcome === "recommended" && (
            <>
              <div className="flex items-end justify-between gap-4">
                <div>
                  <span className={BRAND_TAG}>结构化推荐</span>
                  <h2 className="mt-0.5 text-lg">最多显示三个有效匹配</h2>
                </div>
                <div className="grid justify-items-end gap-1">
                  <button
                    className="inline-flex min-h-10 cursor-pointer items-center justify-center gap-2 rounded-[0.65rem] border border-border bg-surface px-3 text-sm font-bold text-brand-strong disabled:cursor-not-allowed disabled:opacity-50"
                    ref={compareTriggerRef}
                    type="button"
                    disabled={selected.length < 2}
                    onClick={() => setComparisonOpen(true)}
                  >
                    对比已选（{selected.length}）
                  </button>
                  {comparisonError && (
                    <span className="text-sm text-warning" role="alert">
                      {comparisonError}
                    </span>
                  )}
                </div>
              </div>
              <div className="grid grid-cols-3 gap-3 max-[980px]:grid-cols-1">
                {recommendations.map((item, index) => (
                  <RecommendationCard
                    key={item.sku_id}
                    item={item}
                    rank={index + 1}
                    inComparison={selected.some((choice) => choice.sku_id === item.sku_id)}
                    selectedSkuIds={selected.map((choice) => choice.sku_id)}
                    onSelectSku={
                      recommendationContext
                        ? (skuId) => onSelectSku?.(skuId, recommendationContext)
                        : undefined
                    }
                    onAddToCompare={() => toggleChoice(mainChoice(item))}
                    onAddAlternative={(alternative) => toggleChoice(alternative)}
                  />
                ))}
              </div>
              <ComparisonDrawer
                open={comparisonOpen}
                choices={selected}
                onClose={() => setComparisonOpen(false)}
                restoreFocus={compareTriggerRef}
              />
            </>
          )}
        </>
      )}
    </section>
  );
}
