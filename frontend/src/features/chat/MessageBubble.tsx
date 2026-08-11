import type { ChatMessage } from "./chatTypes";

function responseLabel(status: string): string {
  if (status === "confirmation_required") return "等待确认";
  if (status === "failed") return "请求失败";
  if (status === "cancelled") return "已取消";
  return "已完成";
}

export function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  return <article className={`message-row ${isUser ? "message-row-user" : "message-row-assistant"}`}><div className="message-avatar" aria-hidden="true">{isUser ? "你" : "S"}</div><div className="message-bubble"><div className="message-meta">{isUser ? "你" : "ShopMind"}</div><p>{message.content}</p>{message.response && <div className={`response-status response-status-${message.response.status}`}><span aria-hidden="true">●</span>{responseLabel(message.response.status)}{message.response.pending_action_id && <span> · 已生成待确认操作</span>}</div>}</div></article>;
}
