import type { ChatResponse } from "../../api/contracts";
import { isTerminalChatResponsePayload, type AgentEvent } from "../../api/sseTypes";

export type StreamStatus =
  | "idle"
  | "connecting"
  | "running"
  | "awaiting_confirmation"
  | "succeeded"
  | "failed"
  | "cancelled";

export interface StreamProgress {
  sequence: number;
  label: string;
  agentName: string | null;
}

export interface StreamState {
  status: StreamStatus;
  lastSequence: number;
  progress: StreamProgress[];
  response: ChatResponse | null;
  error: string | null;
}

export const initialStreamState: StreamState = {
  status: "idle",
  lastSequence: 0,
  progress: [],
  response: null,
  error: null,
};

type StreamAction =
  | { type: "start" }
  | { type: "event"; event: AgentEvent }
  | { type: "eof" }
  | { type: "cancel" }
  | { type: "error"; message: string };

function progressLabel(event: AgentEvent): string {
  const type = event.event_type;
  if (type.includes("attempt") || type.includes("retry")) return "正在处理一次受控尝试";
  if (type.includes("plan") || type.includes("supervisor")) return "正在拆解购物需求";
  if (type.includes("product")) return "正在检索商品信息";
  if (type.includes("rag") || type.includes("document")) return "正在核对商品与规则信息";
  if (type.includes("preference")) return "正在整理偏好";
  if (type.includes("decision")) return "正在整理决策建议";
  if (type.includes("tool")) return "正在读取必要信息";
  if (type.includes("started")) return "已开始处理你的需求";
  if (type.includes("completed")) return "已完成一项处理";
  return "正在处理你的需求";
}

function terminalStatus(response: ChatResponse): StreamStatus {
  if (response.status === "confirmation_required") return "awaiting_confirmation";
  if (response.status === "failed") return "failed";
  if (response.status === "cancelled") return "cancelled";
  return "succeeded";
}

export function streamReducer(state: StreamState, action: StreamAction): StreamState {
  if (action.type === "start") return { ...initialStreamState, status: "connecting" };
  if (action.type === "cancel") return { ...state, status: "cancelled", response: null, error: null };
  if (action.type === "error") return { ...state, status: "failed", response: null, error: action.message };
  if (action.type === "eof") {
    return state.status === "connecting" || state.status === "running"
      ? { ...state, status: "failed", response: null, error: "流已结束，但后端没有返回最终结果。" }
      : state;
  }
  if (action.event.visibility !== "client") return state;
  if (action.event.sequence <= state.lastSequence) return state;

  const event = action.event;
  if (event.event_type === "run.result") {
    if (!isTerminalChatResponsePayload(event.payload)) {
      return { ...state, lastSequence: event.sequence, status: "failed", response: null, error: "后端返回的最终结果格式无法识别。" };
    }
    return {
      ...state,
      lastSequence: event.sequence,
      status: terminalStatus(event.payload),
      response: event.payload,
      error: event.payload.status === "failed" ? event.payload.answer : null,
    };
  }
  if (event.event_type === "run.failed") {
    return { ...state, lastSequence: event.sequence, status: "failed", response: null, error: "后端运行失败，请重试。" };
  }

  const progress = event.event_type === "run.started"
    ? state.progress
    : [...state.progress, {
      sequence: event.sequence,
      label: progressLabel(event),
      agentName: event.agent_name ?? null,
    }].slice(-6);
  return { ...state, lastSequence: event.sequence, status: "running", progress, error: null };
}
