import type { RecommendationResult } from "../api/contracts";
import type { AgentEvent } from "../api/sseTypes";
import { ALL_DEMO_PRODUCTS } from "./fixtures/catalog";
import {
  clarificationRecommendation,
  degradedEvidenceRecommendation,
  monitorRecommendation,
  noMatchRecommendation,
  normalLaptopRecommendation,
  skuLookupAnswer,
} from "./fixtures/chat-stream";

export type ChatScenario =
  | { kind: "sku_lookup"; answer: string }
  | { kind: "recommendation"; result: RecommendationResult };

const LOW_BUDGET_PATTERN = /\b([1-9]\d{2,3})\b/;

/** Picks one of the five scenarios docs/frontend_redesign_v2_plan_3.md §3 calls for
 *  (正常 / 预算冲突 / 证据降级 / 确认前价格变动 / 任务修订与恢复 — the last one is entirely
 *  the existing task-fixture demo, not chat) from the free-text message. No real NLU: a
 *  demo only needs to be legible, not clever, and every trigger here is something a person
 *  reading the quick-prompt buttons or typing a natural follow-up would actually hit. */
export function selectScenario(message: string): ChatScenario {
  const text = message.trim();

  const skuMatch = ALL_DEMO_PRODUCTS.find((product) => text.includes(product.product_code));
  if (skuMatch) {
    const answer = skuLookupAnswer(skuMatch.product_code);
    if (answer) return { kind: "sku_lookup", answer };
  }

  const budgetMatch = text.match(LOW_BUDGET_PATTERN);
  if (text.includes("预算") && budgetMatch && Number(budgetMatch[1]) < 3000) {
    return { kind: "recommendation", result: noMatchRecommendation() };
  }

  if (text.length > 0 && text.length < 8) {
    return { kind: "recommendation", result: clarificationRecommendation() };
  }

  if (text.includes("显示器") || text.includes("带鱼屏") || text.includes("显示屏")) {
    return { kind: "recommendation", result: monitorRecommendation() };
  }

  if (text.includes("证据") || text.includes("文档") || text.includes("降级")) {
    return { kind: "recommendation", result: degradedEvidenceRecommendation() };
  }

  return { kind: "recommendation", result: normalLaptopRecommendation() };
}

const PROGRESS_STEPS: Array<{ event_type: string; agent_name: string | null }> = [
  { event_type: "run.started", agent_name: null },
  { event_type: "product_agent.started", agent_name: "product_agent" },
  { event_type: "product_agent.completed", agent_name: "product_agent" },
  { event_type: "rag_agent.started", agent_name: "rag_agent" },
  { event_type: "rag_agent.completed", agent_name: "rag_agent" },
  { event_type: "write_handoff.started", agent_name: "write_handoff" },
];

/** Builds the client-visible event sequence a real streamed run would emit before its
 *  terminal `run.result` — same shape `streamReducer.ts` already knows how to fold into
 *  `ExecutionTimeline`'s progress list, so the demo's "实时执行进度" looks identical to a
 *  real run, just on a clock the demo controls instead of a live backend's. */
export function buildProgressEvents(traceId: string): AgentEvent[] {
  return PROGRESS_STEPS.map((step, index) => ({
    sequence: index + 1,
    event_type: step.event_type,
    timestamp: new Date().toISOString(),
    agent_name: step.agent_name,
    trace_id: traceId,
    visibility: "client",
    payload: {},
  }));
}

export function buildTerminalEvent(
  sequence: number,
  traceId: string,
  payload: unknown,
): AgentEvent {
  return {
    sequence,
    event_type: "run.result",
    timestamp: new Date().toISOString(),
    agent_name: null,
    trace_id: traceId,
    visibility: "client",
    payload: payload as Record<string, unknown>,
  };
}

export function sseFrame(event: AgentEvent): string {
  return `id: ${event.sequence}\nevent: ${event.event_type}\ndata: ${JSON.stringify(event)}\n\n`;
}
