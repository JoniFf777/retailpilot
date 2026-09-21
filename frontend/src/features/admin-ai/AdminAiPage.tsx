import { useQuery } from "@tanstack/react-query";

interface AiHealth {
  schema_version: string;
  status: string;
  evidence: { evidence: Record<string, number>; tasks: Record<string, number> };
  rocketmq: string;
  models: Array<{ candidate_id: string; operation: string; state: string }>;
}

async function readHealth(signal?: AbortSignal): Promise<AiHealth> {
  const response = await fetch("/api/admin/ai/health", {
    signal,
    headers: { Accept: "application/json" },
  });
  if (!response.ok)
    throw new Error(response.status === 404 ? "AI 运维控制台未启用" : "无法读取 AI 运维状态");
  return response.json() as Promise<AiHealth>;
}

export function AdminAiPage() {
  const query = useQuery({
    queryKey: ["admin-ai-health"],
    queryFn: ({ signal }) => readHealth(signal),
  });
  const evidence = query.data?.evidence.evidence ?? {};
  const tasks = query.data?.evidence.tasks ?? {};
  return (
    <section className="status-page" aria-labelledby="admin-ai-title">
      <div className="page-heading">
        <div>
          <p className="eyebrow">SHOPPING EVIDENCE OPERATIONS</p>
          <h1 id="admin-ai-title">AI 运维</h1>
          <p className="page-lede">仅管理员可见的购物证据、入库任务与可选 Outbox 发布状态。</p>
        </div>
        <button className="button secondary" type="button" onClick={() => void query.refetch()}>
          重新检查
        </button>
      </div>
      {query.isPending && (
        <p className="state-card" role="status">
          正在读取 AI 运维状态…
        </p>
      )}
      {query.isError && (
        <div className="state-card error-state" role="alert">
          {query.error instanceof Error ? query.error.message : "AI 运维状态不可用"}
        </div>
      )}
      {query.data && (
        <div className="status-summary-grid">
          <article className="status-card">
            <span className="card-kicker">EVIDENCE</span>
            <h2>{Object.values(evidence).reduce((total, value) => total + value, 0)}</h2>
            <p>当前购物证据版本</p>
          </article>
          <article className="status-card">
            <span className="card-kicker">INGESTION</span>
            <h2>{Object.values(tasks).reduce((total, value) => total + value, 0)}</h2>
            <p>入库任务总数</p>
          </article>
          <article className="status-card">
            <span className="card-kicker">OUTBOX</span>
            <h2>独立</h2>
            <p>{query.data.rocketmq}</p>
          </article>
          <article className="status-card">
            <span className="card-kicker">MODELS</span>
            <h2>{query.data.models.length}</h2>
            <p>候选模型健康快照</p>
          </article>
        </div>
      )}
    </section>
  );
}
