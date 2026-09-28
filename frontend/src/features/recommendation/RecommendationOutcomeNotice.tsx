import type { RecommendationResult } from "../../api/contracts";

const NOTICE = "grid gap-2 rounded-md border border-warning/25 bg-warning-soft p-4";
const NOTICE_HEADING = "m-0 text-[0.92rem] text-warning";
const NOTICE_BODY = "m-0 leading-relaxed text-text-muted";
const NOTICE_BUTTON =
  "inline-flex min-h-10 cursor-pointer items-center justify-center justify-self-start gap-2 rounded-[0.65rem] border border-border bg-surface px-3 text-sm font-bold text-brand-strong disabled:cursor-not-allowed disabled:opacity-50";

export function RecommendationOutcomeNotice({
  result,
  onFillPrompt,
}: {
  result: RecommendationResult;
  onFillPrompt: (prompt: string) => void;
}) {
  if (result.outcome === "no_match")
    return (
      <section className={NOTICE} role="status">
        <h3 className={NOTICE_HEADING}>暂时没有符合条件的商品</h3>
        <p className={NOTICE_BODY}>{result.no_match_reason ?? "当前条件下没有可推荐的商品。"}</p>
        <button
          className={NOTICE_BUTTON}
          type="button"
          onClick={() => onFillPrompt("我可以调整预算、用途、内存或重量要求：")}
        >
          调整需求
        </button>
      </section>
    );
  if (result.outcome === "clarification_required")
    return (
      <section className={NOTICE} role="status">
        <h3 className={NOTICE_HEADING}>还需要补充一点信息</h3>
        <p className={NOTICE_BODY}>{result.clarification_question ?? "请补充你的关键选购条件。"}</p>
        {(result.missing_fields ?? []).length > 0 && (
          <p className="m-0 text-sm text-text-muted">待补充：{result.missing_fields?.join("、")}</p>
        )}
        <button
          className={NOTICE_BUTTON}
          type="button"
          onClick={() => onFillPrompt(result.clarification_question ?? "请补充我的选购条件：")}
        >
          补充信息
        </button>
      </section>
    );
  return null;
}
