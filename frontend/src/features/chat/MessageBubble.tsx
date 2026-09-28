import type { ChatMessage } from "./chatTypes";

const STATUS_TONE: Record<string, string> = {
  completed: "text-success",
  confirmation_required: "text-warning",
  failed: "text-danger",
};

function responseLabel(status: string): string {
  if (status === "confirmation_required") return "等待确认";
  if (status === "failed") return "请求失败";
  if (status === "cancelled") return "已取消";
  return "已完成";
}

export function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  return (
    <article
      className={`flex max-w-[88%] items-start gap-2.5 ${isUser ? "ml-auto flex-row-reverse" : ""}`}
    >
      <div
        className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border border-solid text-xs font-extrabold ${isUser ? "border-border bg-[#e8efec] text-text-muted" : "border-brand bg-brand text-white"}`}
        aria-hidden="true"
      >
        {isUser ? "你" : "R"}
      </div>
      <div
        className={`rounded-tl-none rounded-tr-2xl rounded-br-2xl rounded-bl-2xl border border-solid px-3.5 py-3 ${isUser ? "rounded-tl-2xl rounded-tr-none border-[#c9e9dd] bg-brand-soft" : "border-[#e1ece7] bg-[#f3f7f5]"}`}
      >
        <div className="mb-1.5 text-xs font-extrabold text-text-subtle">
          {isUser ? "你" : "RetailPilot"}
        </div>
        <p className="m-0 text-sm leading-relaxed whitespace-pre-wrap">{message.content}</p>
        {message.response && (
          <div
            className={`mt-2.5 flex items-center gap-1.5 text-xs ${STATUS_TONE[message.response.status] ?? ""}`}
          >
            <span aria-hidden="true">●</span>
            {responseLabel(message.response.status)}
            {message.response.pending_action_id && <span> · 已生成待确认操作</span>}
          </div>
        )}
      </div>
    </article>
  );
}
