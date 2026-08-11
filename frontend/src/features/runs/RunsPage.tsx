import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { shopMindApi } from "../../api/client";
import { useSession } from "../../app/useSession";
import { chatErrorMessage } from "../chat/chatErrors";

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

export function RunsPage() {
  const { isDevelopment, userId, setUserId } = useSession();
  const effectiveOwner = isDevelopment ? userId.trim() : "";
  const [selectorType, setSelectorType] = useState<"run_id" | "trace_id">("run_id");
  const [selectorValue, setSelectorValue] = useState("");
  const [submitted, setSubmitted] = useState<{ type: "run_id" | "trace_id"; value: string } | null>(null);
  const [eventLimit, setEventLimit] = useState(50);
  const runQuery = useQuery({
    queryKey: ["owner-run", effectiveOwner, submitted?.type, submitted?.value, eventLimit],
    queryFn: () => shopMindApi.inspectRun({ user_id: effectiveOwner, [submitted?.type ?? "run_id"]: submitted?.value, event_limit: eventLimit }),
    enabled: Boolean(effectiveOwner && submitted?.value),
  });

  function inspect(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = selectorValue.trim();
    if (value && effectiveOwner) setSubmitted({ type: selectorType, value });
  }

  return (
    <section className="runs-page" aria-labelledby="runs-title">
      <div className="page-heading"><div><p className="eyebrow">PAYLOAD-FREE OBSERVABILITY</p><h1 id="runs-title">运行记录</h1><p>只查看当前 owner 的运行元数据和 client-visible 事件摘要，不展示请求正文、结果正文或原始 payload。</p></div></div>
      {isDevelopment ? <label className="identity-strip" htmlFor="runs-user-id">开发用户标识<input id="runs-user-id" value={userId} onChange={(event) => setUserId(event.target.value)} /><span>切换身份会清空前端 Query cache。</span></label> : <div className="notice-card">生产身份由可信入口绑定，浏览器不会自行构造身份凭据。</div>}
      <form className="run-search-card" onSubmit={inspect}>
        <div className="run-search-heading"><div><p className="eyebrow">EXACT OWNER SELECTOR</p><h2>查找一次运行</h2></div><span>必须提供 run ID 或 trace ID 之一</span></div>
        <div className="run-search-controls"><select aria-label="运行选择器类型" onChange={(event) => setSelectorType(event.target.value as "run_id" | "trace_id")} value={selectorType}><option value="run_id">Run ID</option><option value="trace_id">Trace ID</option></select><input aria-label="运行选择器值" data-testid="run-selector" onChange={(event) => setSelectorValue(event.target.value)} placeholder="输入 opaque selector" value={selectorValue} /><input aria-label="事件数量上限" min="1" max="100" onChange={(event) => setEventLimit(Number(event.target.value) || 50)} type="number" value={eventLimit} /><button className="primary-button" data-testid="run-inspect" disabled={!effectiveOwner || !selectorValue.trim()} type="submit">查看运行</button></div>
      </form>
      {runQuery.isLoading && <div className="loading-panel" role="status">正在读取 payload-free 运行摘要…</div>}
      {runQuery.isError && <div className="error-state standalone" role="alert"><div><strong>无法读取运行记录</strong><p>{chatErrorMessage(runQuery.error)}</p></div><button className="text-button" onClick={() => void runQuery.refetch()} type="button">重试</button></div>}
      {runQuery.data && <article className="run-detail-card"><div className="run-detail-heading"><div><p className="eyebrow">RUN SUMMARY</p><h2>{runQuery.data.run_id}</h2><p>Trace {runQuery.data.trace_id}</p></div><span className={`run-status run-status-${runQuery.data.status}`}>{runQuery.data.status}</span></div><div className="run-facts"><div><span>Thread</span><strong>{runQuery.data.thread_id}</strong></div><div><span>Operation</span><strong>{runQuery.data.operation}</strong></div><div><span>Mode</span><strong>{runQuery.data.mode}</strong></div><div><span>Started</span><strong>{formatDate(runQuery.data.started_at)}</strong></div><div><span>Events</span><strong>{runQuery.data.client_event_count}{runQuery.data.events_truncated ? "+" : ""}</strong></div><div><span>Steps</span><strong>{runQuery.data.usage.step_count}</strong></div></div><div className="timeline-heading"><h3>Client-visible timeline</h3><span>不包含 event payload</span></div><ol className="run-timeline">{runQuery.data.events.map((event) => <li key={event.sequence}><span className="timeline-sequence">{event.sequence}</span><div><strong>{event.event_type}</strong><span>{event.agent_name ?? "ShopMind runtime"} · {formatDate(event.created_at)}</span></div></li>)}</ol></article>}
      {!runQuery.data && !runQuery.isLoading && !runQuery.isError && <div className="empty-panel">输入当前 owner 的 opaque run/trace selector 开始查看。</div>}
    </section>
  );
}
