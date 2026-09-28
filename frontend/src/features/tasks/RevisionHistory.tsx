import type { TaskStepView } from "../../api/contracts";
import { Card } from "../../components/primitives";
import { SECTION_HEADING } from "../../components/textPatterns";

const STEP_DOT_TONE: Record<string, string> = {
  completed: "bg-success",
  running: "bg-warning",
  failed: "bg-danger",
};

function stepDotTone(status: string): string {
  return STEP_DOT_TONE[status] ?? "bg-text-subtle";
}

/** Only renders once a local repair has actually produced a second plan revision — the
 *  common case (one revision) shows nothing, matching how RecommendationCard's hard/soft
 *  split shows nothing extra until there's real data to split. Groups `task.steps` (which
 *  mixes every revision) by `plan_revision` so it's visible which steps a repair reused
 *  as-is (absent from the new revision's group, still `completed` in an earlier one) versus
 *  which it superseded and re-ran. */
export function RevisionHistory({
  steps,
  activeRevision,
}: {
  steps: TaskStepView[];
  activeRevision: number;
}) {
  const revisions = [...new Set(steps.map((step) => step.plan_revision))].sort((a, b) => a - b);
  if (revisions.length < 2) return null;
  return (
    <Card as="article" className="grid gap-4" aria-label="计划修订历史">
      <div className={SECTION_HEADING}>
        <h2 className="m-0 text-xl">修订历史</h2>
        <span className="text-sm text-text-muted">{revisions.length} 个版本</span>
      </div>
      <ol className="m-0 grid gap-3.5 p-0">
        {revisions.map((revision) => (
          <li
            className={`grid gap-1.5 border-l-[3px] border-solid pl-3 ${revision === activeRevision ? "border-brand" : "border-border-strong"}`}
            key={revision}
          >
            <span className="text-sm font-extrabold text-brand-strong">
              修订 {revision}
              {revision === activeRevision ? " · 当前" : ""}
            </span>
            <ul className="m-0 flex list-none flex-wrap gap-x-4 gap-y-2 p-0">
              {steps
                .filter((step) => step.plan_revision === revision)
                .map((step) => (
                  <li className="flex items-center gap-1.5 text-sm text-text-muted" key={step.key}>
                    <span className={`h-2.5 w-2.5 rounded-full ${stepDotTone(step.status)}`} />
                    {step.key}
                    <em className="text-xs text-text-subtle not-italic">{step.status}</em>
                  </li>
                ))}
            </ul>
          </li>
        ))}
      </ol>
    </Card>
  );
}
