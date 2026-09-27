import type { TaskStepView } from "../../api/contracts";

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
    <article className="task-panel revision-history" aria-label="计划修订历史">
      <div className="section-heading">
        <h2>修订历史</h2>
        <span>{revisions.length} 个版本</span>
      </div>
      <ol className="revision-list">
        {revisions.map((revision) => (
          <li className="revision-entry" data-active={revision === activeRevision} key={revision}>
            <span className="revision-badge">
              修订 {revision}
              {revision === activeRevision ? " · 当前" : ""}
            </span>
            <ul className="revision-steps">
              {steps
                .filter((step) => step.plan_revision === revision)
                .map((step) => (
                  <li key={step.key}>
                    <span className={`task-step-dot task-step-${step.status}`} />
                    {step.key}
                    <em>{step.status}</em>
                  </li>
                ))}
            </ul>
          </li>
        ))}
      </ol>
    </article>
  );
}
