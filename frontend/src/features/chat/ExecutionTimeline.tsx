import type { StreamProgress } from "./streamReducer";

const AGENT_LABELS: Record<string, string> = {
  product_agent: "商品分析",
  rag_agent: "证据检索",
  preference_agent: "偏好整理",
  write_handoff: "结果整理",
  confirmation_boundary: "确认边界",
  model_gateway: "模型网关",
};

const AGENT_TONES: Record<string, string> = {
  product_agent: "text-agent-product",
  rag_agent: "text-agent-rag",
  preference_agent: "text-agent-preference",
};

const AGENT_DOT_TONES: Record<string, string> = {
  product_agent: "bg-agent-product",
  rag_agent: "bg-agent-rag",
  preference_agent: "bg-agent-preference",
};

function agentLabel(agentName: string | null): string | null {
  if (!agentName) return null;
  return AGENT_LABELS[agentName] ?? agentName;
}

export function ExecutionTimeline({
  progress,
  lastSequence,
}: {
  progress: StreamProgress[];
  lastSequence: number;
}) {
  return (
    <div className="border-b border-border bg-surface-soft px-5.5 py-3.5" aria-live="polite">
      <div className="flex justify-between text-xs font-extrabold text-brand-strong">
        <span>实时执行进度</span>
        <span className="font-medium text-text-subtle">{lastSequence} 个事件</span>
      </div>
      <ol className="m-0 mt-2.5 flex list-none flex-col p-0">
        {progress.map((item) => {
          const tone = (item.agentName && AGENT_TONES[item.agentName]) || "text-text-subtle";
          const dotTone = (item.agentName && AGENT_DOT_TONES[item.agentName]) || "bg-text-subtle";
          return (
            <li className="relative flex gap-2.5 py-1.5" key={item.sequence}>
              <span
                className={`relative z-10 mt-1.5 h-2 w-2 shrink-0 rounded-full ${dotTone}`}
                aria-hidden="true"
              />
              <div className="flex flex-col gap-0.5 text-xs">
                {item.agentName && (
                  <span className={`text-[0.64rem] font-bold tracking-wide uppercase ${tone}`}>
                    {agentLabel(item.agentName)}
                  </span>
                )}
                <span className="text-text-muted">{item.label}</span>
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
