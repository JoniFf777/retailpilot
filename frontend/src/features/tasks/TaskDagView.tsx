import type { PlanProposal, PlanStep, StepStatus, TaskStepView } from "../../api/contracts";

const NODE_WIDTH = 168;
const NODE_HEIGHT = 52;
const ROW_GAP = 52;
const COL_GAP = 20;
const PADDING = 16;

type LaidOutNode = {
  step: PlanStep;
  current: TaskStepView | undefined;
  x: number;
  y: number;
};

function layerOf(steps: PlanStep[]): PlanStep[][] {
  const byKey = new Map(steps.map((step) => [step.key, step]));
  const depthCache = new Map<string, number>();
  function depthOf(key: string, stack: readonly string[]): number {
    const cached = depthCache.get(key);
    if (cached !== undefined) return cached;
    if (stack.includes(key)) return 0; // a cycle would be a backend bug; render it flat rather than loop
    const deps = byKey.get(key)?.depends_on ?? [];
    const depth = deps.length
      ? 1 + Math.max(...deps.map((dep: string) => depthOf(dep, [...stack, key])))
      : 0;
    depthCache.set(key, depth);
    return depth;
  }
  const layers: PlanStep[][] = [];
  for (const step of steps) {
    const depth = depthOf(step.key, []);
    (layers[depth] ??= []).push(step);
  }
  return layers;
}

function statusTone(status: StepStatus | undefined): string {
  if (status === "completed") return "var(--color-success)";
  if (status === "running") return "var(--color-warning)";
  if (status === "failed") return "var(--color-danger)";
  return "var(--color-text-subtle)"; // pending / skipped / superseded / unknown
}

/** Hand-drawn layered DAG (no graph library — capped at 12 steps by the backend, see
 *  app/shopping_tasks/contracts.py MAX_PLAN_STEPS). Columns by dependency depth, bezier
 *  edges. Reads structure from `plan.steps[].depends_on`; colors each node from the current
 *  revision's live execution status in `steps`. This is a supplementary visual — the
 *  existing text step list below it remains the accessible source of truth. */
export function TaskDagView({ plan, steps }: { plan: PlanProposal; steps: TaskStepView[] }) {
  const currentByKey = new Map(
    steps.filter((step) => step.plan_revision === plan.revision).map((step) => [step.key, step]),
  );
  const layers = layerOf(plan.steps);
  const width =
    Math.max(...layers.map((layer) => layer.length)) * (NODE_WIDTH + COL_GAP) -
    COL_GAP +
    PADDING * 2;
  const height = layers.length * (NODE_HEIGHT + ROW_GAP) - ROW_GAP + PADDING * 2;

  const nodes: LaidOutNode[] = [];
  layers.forEach((layer, rowIndex) => {
    const rowWidth = layer.length * (NODE_WIDTH + COL_GAP) - COL_GAP;
    const rowStartX = (width - rowWidth) / 2;
    layer.forEach((step, colIndex) => {
      nodes.push({
        step,
        current: currentByKey.get(step.key),
        x: rowStartX + colIndex * (NODE_WIDTH + COL_GAP),
        y: PADDING + rowIndex * (NODE_HEIGHT + ROW_GAP),
      });
    });
  });
  const byKey = new Map(nodes.map((node) => [node.step.key, node]));

  return (
    <svg
      aria-label={`任务步骤依赖图：${plan.steps.length} 个步骤，${layers.length} 层依赖`}
      className="task-dag mb-1 h-auto w-full"
      role="img"
      viewBox={`0 0 ${width} ${height}`}
    >
      <g className="task-dag-edges">
        {nodes.flatMap((node) =>
          (node.step.depends_on ?? []).flatMap((depKey: string) => {
            const from = byKey.get(depKey);
            if (!from) return [];
            const fromX = from.x + NODE_WIDTH / 2;
            const fromY = from.y + NODE_HEIGHT;
            const toX = node.x + NODE_WIDTH / 2;
            const toY = node.y;
            const midY = (fromY + toY) / 2;
            return [
              <path
                className="task-dag-edge"
                d={`M ${fromX} ${fromY} C ${fromX} ${midY}, ${toX} ${midY}, ${toX} ${toY}`}
                fill="none"
                key={`${depKey}->${node.step.key}`}
                style={{ stroke: "var(--color-border-strong)", strokeWidth: 1.5 }}
              />,
            ];
          }),
        )}
      </g>
      <g className="task-dag-nodes">
        {nodes.map(({ step, current, x, y }, index) => (
          <g key={step.key} transform={`translate(${x}, ${y})`}>
            <rect
              className="task-dag-node"
              height={NODE_HEIGHT}
              rx={10}
              style={{
                fill: "var(--color-surface)",
                stroke: statusTone(current?.status),
                strokeWidth: 2,
              }}
              width={NODE_WIDTH}
            />
            {/* Prefixed with the node's sequence number so this label is never the bare
                `step.key`/`step.role` text that the plain step list below also renders —
                two elements with byte-identical own text would make that list's existing
                `getByText(...)` assertions ambiguous (see TaskDetailPage.test.tsx). */}
            <text
              className="task-dag-node-key"
              style={{ fill: "var(--color-text-primary)", fontSize: 12, fontWeight: 750 }}
              x={12}
              y={20}
            >
              #{index + 1} {step.key}
            </text>
            <text
              className="task-dag-node-meta"
              style={{ fill: "var(--color-text-subtle)", fontSize: 10 }}
              x={12}
              y={38}
            >
              角色 {step.role}
            </text>
            <circle cx={NODE_WIDTH - 14} cy={14} fill={statusTone(current?.status)} r={5} />
          </g>
        ))}
      </g>
    </svg>
  );
}
