import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { PlanProposal, PlanStep, TaskStepView } from "../../api/contracts";
import { TaskDagView } from "./TaskDagView";

function planStep(overrides: Partial<PlanStep> & Pick<PlanStep, "key">): PlanStep {
  return {
    capability: "extract_goal",
    role: "coordinator",
    depends_on: [],
    output_kind: "x",
    read_only: true,
    ...overrides,
  };
}

function plan(steps: PlanStep[], revision = 1): PlanProposal {
  return {
    schema_version: "plan-proposal.v1",
    revision,
    mode: "offline",
    reason: "deterministic_offline_plan",
    fingerprint: "",
    steps,
  };
}

function execStep(overrides: Partial<TaskStepView> & Pick<TaskStepView, "key">): TaskStepView {
  return {
    plan_revision: 1,
    capability: "extract_goal",
    role: "coordinator",
    status: "pending",
    attempt_count: 0,
    has_lease: false,
    ...overrides,
  };
}

describe("TaskDagView", () => {
  it("renders one node per plan step and one edge per dependency", () => {
    const { container } = render(
      <TaskDagView
        plan={plan([
          planStep({ key: "goal" }),
          planStep({ key: "candidates", depends_on: ["goal"] }),
        ])}
        steps={[]}
      />,
    );
    expect(screen.getByRole("img", { name: /2 个步骤/ })).toBeInTheDocument();
    expect(container.querySelectorAll(".task-dag-node")).toHaveLength(2);
    expect(container.querySelectorAll(".task-dag-edge")).toHaveLength(1);
  });

  it("puts independent parallel steps on the same layer row", () => {
    const { container } = render(
      <TaskDagView
        plan={plan([
          planStep({ key: "goal" }),
          planStep({ key: "candidates", depends_on: ["goal"] }),
          planStep({ key: "evidence", depends_on: ["goal"] }),
          planStep({ key: "bundle", depends_on: ["candidates", "evidence"] }),
        ])}
        steps={[]}
      />,
    );
    const groups = Array.from(container.querySelectorAll(".task-dag-nodes > g"));
    const yOf = (index: number) =>
      groups[index]?.getAttribute("transform")?.match(/, (\d+)\)/)?.[1];
    // Layout order is goal, then its two dependents (same row), then bundle.
    expect(yOf(1)).toBe(yOf(2));
    expect(yOf(0)).not.toBe(yOf(1));
    expect(yOf(2)).not.toBe(yOf(3));
    // goal->candidates, goal->evidence, candidates->bundle, evidence->bundle.
    expect(container.querySelectorAll(".task-dag-edge")).toHaveLength(4);
  });

  it("colors a node from the current revision's live status, not the plan's static shape", () => {
    const { container } = render(
      <TaskDagView
        plan={plan([planStep({ key: "bundle" })])}
        steps={[execStep({ key: "bundle", status: "failed" })]}
      />,
    );
    const node = container.querySelector(".task-dag-node");
    expect(node).toHaveStyle({ stroke: "var(--color-danger)" });
  });

  it("ignores a step's status from a superseded earlier revision", () => {
    const { container } = render(
      <TaskDagView
        plan={plan([planStep({ key: "bundle" })], 2)}
        steps={[
          execStep({ key: "bundle", plan_revision: 1, status: "failed" }),
          execStep({ key: "bundle", plan_revision: 2, status: "running" }),
        ]}
      />,
    );
    const node = container.querySelector(".task-dag-node");
    expect(node).toHaveStyle({ stroke: "var(--color-warning)" });
  });
});
