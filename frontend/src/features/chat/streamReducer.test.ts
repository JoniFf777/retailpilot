import { describe, expect, it } from "vitest";
import type { AgentEvent } from "../../api/sseTypes";
import { initialStreamState, streamReducer } from "./streamReducer";

function event(sequence: number, eventType: string, payload: Record<string, unknown> = {}, visibility: AgentEvent["visibility"] = "client"): AgentEvent {
  return {
    sequence,
    event_type: eventType,
    timestamp: "2026-07-26T00:00:00Z",
    visibility,
    payload,
  };
}

describe("ordered stream reducer", () => {
  it("ignores duplicate and out-of-order events", () => {
    let state = streamReducer(initialStreamState, { type: "start" });
    state = streamReducer(state, { type: "event", event: event(2, "product.completed") });
    state = streamReducer(state, { type: "event", event: event(1, "run.started") });
    state = streamReducer(state, { type: "event", event: event(2, "product.completed") });
    expect(state.lastSequence).toBe(2);
    expect(state.progress).toHaveLength(1);
  });

  it("moves to the terminal status from run.result", () => {
    const response = { answer: "建议选择 A。", status: "completed", tool_calls: [], recommendation: { schema_version: "shopmind.recommendation.v1", ranking_policy_version: "v1", request_summary: "开发", outcome: "no_match", no_match_reason: "none", structured_constraints: {}, recommendations: [] } };
    const state = streamReducer(
      streamReducer(initialStreamState, { type: "start" }),
      { type: "event", event: event(3, "run.result", response) },
    );
    expect(state.status).toBe("succeeded");
    expect(state.response?.answer).toBe("建议选择 A。");
    expect(state.response?.recommendation).toEqual(response.recommendation);
  });

  it("represents cancellation and missing terminal output", () => {
    const running = streamReducer(initialStreamState, { type: "start" });
    const cancelled = streamReducer(running, { type: "cancel" });
    const failed = streamReducer(running, { type: "eof" });
    expect(cancelled.status).toBe("cancelled");
    expect(failed.status).toBe("failed");
    expect(cancelled.response).toBeNull();
    expect(failed.response).toBeNull();
  });

  it("never accepts intermediate data as a terminal chat response", () => {
    const state = streamReducer(streamReducer(initialStreamState, { type: "start" }), {
      type: "event", event: event(2, "product.completed", { answer: "not terminal" }),
    });
    expect(state.response).toBeNull();
    expect(state.status).toBe("running");
  });

  it("rejects malformed terminal status and recommendation", () => {
    const running = streamReducer(initialStreamState, { type: "start" });
    const invalidStatus = streamReducer(running, { type: "event", event: event(1, "run.result", { answer: "x", status: "running", tool_calls: [] }) });
    const invalidRecommendation = streamReducer(running, { type: "event", event: event(2, "run.result", { answer: "x", status: "completed", tool_calls: [], recommendation: { schema_version: "shopmind.recommendation.v1", outcome: "recommended", structured_constraints: {}, recommendations: [] } }) });
    expect(invalidStatus.status).toBe("failed");
    expect(invalidRecommendation.status).toBe("failed");
    expect(invalidRecommendation.response).toBeNull();
  });

  it("ignores internal and audit events", () => {
    const running = streamReducer(initialStreamState, { type: "start" });
    const internal = streamReducer(running, { type: "event", event: event(1, "internal.debug", {}, "internal") });
    const audit = streamReducer(internal, { type: "event", event: event(2, "audit.record", {}, "audit") });
    expect(audit.progress).toHaveLength(0);
    expect(audit.lastSequence).toBe(0);
  });
});
