import type { ChatResponse } from "./contracts";

/** SSE is an event transport, not an OpenAPI response body. */
export type EventVisibility = "client" | "internal" | "audit";

export interface AgentEvent {
  sequence: number;
  event_type: string;
  timestamp: string;
  agent_name?: string | null;
  trace_id?: string | null;
  visibility: EventVisibility;
  payload: Record<string, unknown>;
  tool_call_id?: string | null;
}

export interface SseFrame {
  event?: string;
  id?: string;
  data: string;
}

/** Only a terminal `run.result` may be projected into a chat response. */
export function isTerminalChatResponsePayload(value: unknown): value is ChatResponse {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Record<string, unknown>;
  const statuses = new Set(["completed", "confirmation_required", "cancelled", "failed"]);
  if (typeof candidate.answer !== "string" || typeof candidate.status !== "string" || !statuses.has(candidate.status)) return false;
  if (candidate.tool_calls !== undefined && (!Array.isArray(candidate.tool_calls) || !candidate.tool_calls.every((item) => typeof item === "string"))) return false;
  if (candidate.pending_action_id !== undefined && candidate.pending_action_id !== null && typeof candidate.pending_action_id !== "string") return false;
  if (candidate.projection_error !== undefined && candidate.projection_error !== null) {
    if (!candidate.projection_error || typeof candidate.projection_error !== "object") return false;
    const error = candidate.projection_error as Record<string, unknown>;
    if (error.code !== "recommendation_projection_corrupt" || typeof error.message !== "string") return false;
  }
  if (candidate.recommendation !== undefined && candidate.recommendation !== null) {
    if (!candidate.recommendation || typeof candidate.recommendation !== "object") return false;
    const recommendation = candidate.recommendation as Record<string, unknown>;
    const outcomes = new Set(["recommended", "no_match", "clarification_required"]);
    if (recommendation.schema_version !== "shopmind.recommendation.v1" || !outcomes.has(String(recommendation.outcome)) || !recommendation.structured_constraints || typeof recommendation.structured_constraints !== "object") return false;
    if (recommendation.recommendations !== undefined && !Array.isArray(recommendation.recommendations)) return false;
    const recommendations = Array.isArray(recommendation.recommendations) ? recommendation.recommendations : [];
    if (recommendation.outcome === "recommended" && recommendations.length === 0) return false;
    if ((recommendation.outcome === "no_match" || recommendation.outcome === "clarification_required") && recommendations.length > 0) return false;
  }
  return true;
}
