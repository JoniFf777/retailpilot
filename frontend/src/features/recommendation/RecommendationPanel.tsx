import { useEffect, useMemo, useRef, useState } from "react";
import type {
  ProjectionError,
  RecommendationContextView,
  RecommendationResult,
} from "../../api/contracts";
import { ComparisonDrawer } from "./ComparisonDrawer";
import { RecommendationCard } from "./RecommendationCard";
import { RecommendationOutcomeNotice } from "./RecommendationOutcomeNotice";
import { StructuredConstraintsPanel } from "./StructuredConstraintsPanel";
import { mainChoice, recommendationsOf, type RecommendationChoice } from "./recommendationTypes";

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
    <section className="recommendation-panel" aria-label="结构化推荐结果">
      {projectionError && (
        <div className="projection-error" role="alert">
          <strong>推荐详情暂时无法显示</strong>
          <p>结构化推荐暂时无法显示，你仍可以查看文字回答或重新发起请求。</p>
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
            <div className="projection-error" role="status">
              <strong>
                证据状态：
                {recommendation.evidence_status === "unavailable"
                  ? "文档服务不可用"
                  : recommendation.evidence_status === "degraded"
                    ? "部分通道降级"
                    : "尚未找到支持证据"}
              </strong>
              <p>目录价格与库存仍按结构化数据判断，文档型结论请以引用为准。</p>
            </div>
          )}
          {(recommendation.policy_evidence ?? []).length > 0 && (
            <section className="structured-constraints" aria-label="政策依据">
              <span>政策依据</span>
              <ul>
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
              <div className="recommendation-panel-heading">
                <div>
                  <span>结构化推荐</span>
                  <h2>最多显示三个有效匹配</h2>
                </div>
                <div className="comparison-actions">
                  <button
                    ref={compareTriggerRef}
                    type="button"
                    disabled={selected.length < 2}
                    onClick={() => setComparisonOpen(true)}
                  >
                    对比已选（{selected.length}）
                  </button>
                  {comparisonError && <span role="alert">{comparisonError}</span>}
                </div>
              </div>
              <div className="recommendation-grid">
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
