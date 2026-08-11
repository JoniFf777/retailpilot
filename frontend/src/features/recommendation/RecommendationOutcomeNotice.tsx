import type { RecommendationResult } from "../../api/contracts";

export function RecommendationOutcomeNotice({ result, onFillPrompt }: { result: RecommendationResult; onFillPrompt: (prompt: string) => void }) {
  if (result.outcome === "no_match") return <section className="recommendation-notice" role="status"><h3>暂时没有符合条件的商品</h3><p>{result.no_match_reason ?? "当前条件下没有可推荐的商品。"}</p><button type="button" onClick={() => onFillPrompt("我可以调整预算、用途、内存或重量要求：")}>调整需求</button></section>;
  if (result.outcome === "clarification_required") return <section className="recommendation-notice" role="status"><h3>还需要补充一点信息</h3><p>{result.clarification_question ?? "请补充你的关键选购条件。"}</p>{(result.missing_fields ?? []).length > 0 && <p className="notice-fields">待补充：{result.missing_fields?.join("、")}</p>}<button type="button" onClick={() => onFillPrompt(result.clarification_question ?? "请补充我的选购条件：")}>补充信息</button></section>;
  return null;
}
