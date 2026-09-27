import type { StreamProgress } from "./streamReducer";

const AGENT_LABELS: Record<string, string> = {
  product_agent: "商品分析",
  rag_agent: "证据检索",
  preference_agent: "偏好整理",
  write_handoff: "结果整理",
  confirmation_boundary: "确认边界",
  model_gateway: "模型网关",
};

const AGENT_TONES: Record<string, "product" | "rag" | "preference"> = {
  product_agent: "product",
  rag_agent: "rag",
  preference_agent: "preference",
};

function agentLabel(agentName: string | null): string | null {
  if (!agentName) return null;
  return AGENT_LABELS[agentName] ?? agentName;
}

function agentTone(agentName: string | null): string {
  return (agentName && AGENT_TONES[agentName]) || "neutral";
}

export function ExecutionTimeline({
  progress,
  lastSequence,
}: {
  progress: StreamProgress[];
  lastSequence: number;
}) {
  return (
    <div className="stream-progress" aria-live="polite">
      <div className="stream-progress-heading">
        <span>实时执行进度</span>
        <span>{lastSequence} 个事件</span>
      </div>
      <ol className="execution-timeline">
        {progress.map((item) => (
          <li
            className="execution-timeline-item"
            data-tone={agentTone(item.agentName)}
            key={item.sequence}
          >
            <span className="execution-timeline-dot" aria-hidden="true" />
            <div className="execution-timeline-body">
              {item.agentName && (
                <span className="execution-timeline-agent">{agentLabel(item.agentName)}</span>
              )}
              <span className="execution-timeline-label">{item.label}</span>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
