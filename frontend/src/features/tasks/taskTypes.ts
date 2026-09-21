export type TaskKind = "bundle_selection" | "compatibility_diagnosis" | "after_sales_assessment";

export interface ShoppingTaskListItem {
  task_id: string;
  kind: TaskKind;
  status: string;
  mode: "offline" | "agent";
  version: number;
  created_at: string;
}

export interface ShoppingTaskSnapshot {
  task_id: string;
  owner_id: string;
  kind: TaskKind;
  status: string;
  mode: "offline" | "agent";
  version: number;
  goal: {
    kind: TaskKind;
    goal_text: string;
    required_slots: string[];
    open_questions: string[];
    hard_constraints: Record<string, unknown>;
    soft_requirements: Record<string, unknown>;
  };
  plan: {
    steps: Array<{
      key: string;
      capability: string;
      role: string;
      depends_on: string[];
      output_kind: string;
    }>;
  } | null;
  steps: Array<{
    key: string;
    capability: string;
    role: string;
    status: string;
    attempt_count: number;
    output_artifact_id: string | null;
  }>;
  artifacts: Array<{
    id: string;
    kind: string;
    branch: string;
    status: string;
    payload: Record<string, unknown>;
  }>;
  output: Record<string, unknown> | null;
  pending_interaction: Record<string, unknown> | null;
  last_sequence: number;
}
