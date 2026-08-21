import type { ChatResponse } from "../../api/contracts";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  idempotencyKey?: string;
  retryState?: "pending" | "interrupted" | "terminal";
  response?: ChatResponse;
}
