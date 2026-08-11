import type { ChatResponse } from "../../api/contracts";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  response?: ChatResponse;
}
