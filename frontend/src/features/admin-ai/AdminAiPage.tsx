import { useQuery } from "@tanstack/react-query";
import { Button, Card } from "../../components/primitives";
import { EYEBROW, PAGE_HEADING, PAGE_LEDE } from "../../components/textPatterns";

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

function SummaryCard({
  kicker,
  value,
  caption,
}: {
  kicker: string;
  value: string | number;
  caption: string;
}) {
  return (
    <Card as="article" className="grid gap-1.5">
      <span className="text-[0.66rem] font-extrabold tracking-wide text-text-subtle uppercase">
        {kicker}
      </span>
      <h2 className="m-0 text-2xl tracking-tight">{value}</h2>
      <p className="m-0 text-sm text-text-muted">{caption}</p>
    </Card>
  );
}

export function AdminAiPage() {
  const query = useQuery({
    queryKey: ["admin-ai-health"],
    queryFn: ({ signal }) => readHealth(signal),
  });
  const evidence = query.data?.evidence.evidence ?? {};
  const tasks = query.data?.evidence.tasks ?? {};
  return (
    <section aria-labelledby="admin-ai-title" className="grid gap-6">
      <div className={PAGE_HEADING}>
        <div>
          <p className={EYEBROW}>SHOPPING EVIDENCE OPERATIONS</p>
          <h1 id="admin-ai-title">AI 运维</h1>
          <p className={PAGE_LEDE}>仅管理员可见的购物证据、入库任务与可选 Outbox 发布状态。</p>
        </div>
        <Button onClick={() => void query.refetch()} variant="secondary">
          重新检查
        </Button>
      </div>
      {query.isPending && (
        <p className="m-0 text-sm text-text-muted" role="status">
          正在读取 AI 运维状态…
        </p>
      )}
      {query.isError && (
        <Card as="div" className="border-danger/25 bg-danger-soft text-sm text-danger" role="alert">
          {query.error instanceof Error ? query.error.message : "AI 运维状态不可用"}
        </Card>
      )}
      {query.data && (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <SummaryCard
            caption="当前购物证据版本"
            kicker="EVIDENCE"
            value={Object.values(evidence).reduce((total, value) => total + value, 0)}
          />
          <SummaryCard
            caption="入库任务总数"
            kicker="INGESTION"
            value={Object.values(tasks).reduce((total, value) => total + value, 0)}
          />
          <SummaryCard caption={query.data.rocketmq} kicker="OUTBOX" value="独立" />
          <SummaryCard
            caption="候选模型健康快照"
            kicker="MODELS"
            value={query.data.models.length}
          />
        </div>
      )}
    </section>
  );
}
