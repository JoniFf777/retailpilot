import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Badge, Button, Card, Empty, type BadgeTone } from "../../components/primitives";
import { shopMindApi } from "../../api/client";
import { useSession } from "../../app/useSession";
import { chatErrorMessage } from "../chat/chatErrors";

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(
    new Date(value),
  );
}

function runStatusTone(status: string): BadgeTone {
  if (status === "completed") return "success";
  if (status === "failed") return "danger";
  if (status === "confirmation_required") return "warning";
  return "neutral";
}

export function RunsPage() {
  const { isDevelopment, userId, setUserId } = useSession();
  const effectiveOwner = isDevelopment ? userId.trim() : "";
  const [selectorType, setSelectorType] = useState<"run_id" | "trace_id">("run_id");
  const [selectorValue, setSelectorValue] = useState("");
  const [submitted, setSubmitted] = useState<{ type: "run_id" | "trace_id"; value: string } | null>(
    null,
  );
  const [eventLimit, setEventLimit] = useState(50);
  const runQuery = useQuery({
    queryKey: ["owner-run", effectiveOwner, submitted?.type, submitted?.value, eventLimit],
    queryFn: () =>
      shopMindApi.inspectRun({
        user_id: effectiveOwner,
        [submitted?.type ?? "run_id"]: submitted?.value,
        event_limit: eventLimit,
      }),
    enabled: Boolean(effectiveOwner && submitted?.value),
  });

  function inspect(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = selectorValue.trim();
    if (value && effectiveOwner) setSubmitted({ type: selectorType, value });
  }

  return (
    <section aria-labelledby="runs-title" className="grid gap-6">
      <div className="page-heading">
        <div>
          <p className="eyebrow">PAYLOAD-FREE OBSERVABILITY</p>
          <h1 id="runs-title">运行记录</h1>
          <p className="page-lede">
            只查看当前 owner 的运行元数据和 client-visible 事件摘要，不展示请求正文、结果正文或原始
            payload。
          </p>
        </div>
      </div>
      {isDevelopment ? (
        <Card
          as="div"
          className="flex flex-wrap items-center gap-3 bg-white/88 text-sm text-text-muted"
        >
          <label
            className="flex items-center gap-2 font-semibold text-text-primary"
            htmlFor="runs-user-id"
          >
            开发用户标识
            <input
              className="w-45 rounded-sm border border-solid border-border-strong px-2.5 py-1.5 font-normal"
              id="runs-user-id"
              onChange={(event) => setUserId(event.target.value)}
              value={userId}
            />
          </label>
          <span className="text-xs text-text-subtle">切换身份会清空前端 Query cache。</span>
        </Card>
      ) : (
        <Card as="div" className="text-sm text-text-muted">
          生产身份由可信入口绑定，浏览器不会自行构造身份凭据。
        </Card>
      )}
      <Card as="form" className="grid gap-4" onSubmit={inspect}>
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="eyebrow">EXACT OWNER SELECTOR</p>
            <h2 className="m-0 text-xl">查找一次运行</h2>
          </div>
          <span className="text-xs text-text-subtle">必须提供 run ID 或 trace ID 之一</span>
        </div>
        <div className="grid grid-cols-[150px_minmax(0,1fr)_90px_auto] gap-2.5 max-sm:grid-cols-1">
          <select
            aria-label="运行选择器类型"
            className="min-w-0 rounded-sm border border-solid border-border-strong px-2.5 py-1.5"
            onChange={(event) => setSelectorType(event.target.value as "run_id" | "trace_id")}
            value={selectorType}
          >
            <option value="run_id">Run ID</option>
            <option value="trace_id">Trace ID</option>
          </select>
          <input
            aria-label="运行选择器值"
            className="min-w-0 rounded-sm border border-solid border-border-strong px-2.5 py-1.5"
            data-testid="run-selector"
            onChange={(event) => setSelectorValue(event.target.value)}
            placeholder="输入 opaque selector"
            value={selectorValue}
          />
          <input
            aria-label="事件数量上限"
            className="min-w-0 rounded-sm border border-solid border-border-strong px-2.5 py-1.5"
            max="100"
            min="1"
            onChange={(event) => setEventLimit(Number(event.target.value) || 50)}
            type="number"
            value={eventLimit}
          />
          <Button
            data-testid="run-inspect"
            disabled={!effectiveOwner || !selectorValue.trim()}
            type="submit"
          >
            查看运行
          </Button>
        </div>
      </Card>
      {runQuery.isLoading && (
        <p className="m-0 text-sm text-text-muted" role="status">
          正在读取 payload-free 运行摘要…
        </p>
      )}
      {runQuery.isError && (
        <Card
          as="div"
          className="flex flex-wrap items-center justify-between gap-3 border-danger/25 bg-danger-soft"
          role="alert"
        >
          <div>
            <strong className="text-text-primary">无法读取运行记录</strong>
            <p className="m-0 text-sm text-text-muted">{chatErrorMessage(runQuery.error)}</p>
          </div>
          <Button onClick={() => void runQuery.refetch()} size="sm" variant="secondary">
            重试
          </Button>
        </Card>
      )}
      {runQuery.data && (
        <Card as="article" className="grid gap-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="eyebrow">RUN SUMMARY</p>
              <h2 className="overflow-wrap-anywhere m-0 text-xl">{runQuery.data.run_id}</h2>
              <p className="overflow-wrap-anywhere mt-1.5 text-sm text-text-muted">
                Trace {runQuery.data.trace_id}
              </p>
            </div>
            <Badge tone={runStatusTone(runQuery.data.status)}>{runQuery.data.status}</Badge>
          </div>
          <div className="grid grid-cols-[repeat(auto-fit,minmax(150px,1fr))] gap-2.5">
            {[
              ["Thread", runQuery.data.thread_id],
              ["Operation", runQuery.data.operation],
              ["Mode", runQuery.data.mode],
              ["Started", formatDate(runQuery.data.started_at)],
              [
                "Events",
                `${runQuery.data.client_event_count}${runQuery.data.events_truncated ? "+" : ""}`,
              ],
              ["Steps", String(runQuery.data.usage.step_count)],
            ].map(([label, value]) => (
              <div
                className="grid gap-1 rounded-sm border border-solid border-[#e0efe9] bg-surface-soft p-3"
                key={label}
              >
                <span className="overflow-wrap-anywhere text-xs text-text-subtle">{label}</span>
                <strong className="overflow-wrap-anywhere text-sm">{value}</strong>
              </div>
            ))}
          </div>
          <div className="flex items-baseline justify-between gap-3 border-b border-solid border-border pb-3">
            <h3 className="m-0 text-base">Client-visible timeline</h3>
            <span className="text-xs text-text-subtle">不包含 event payload</span>
          </div>
          <ol className="m-0 grid list-none gap-3 p-0">
            {runQuery.data.events.map((event) => (
              <li className="grid grid-cols-[2rem_1fr] items-start gap-3" key={event.sequence}>
                <span className="flex h-8 w-8 items-center justify-center rounded-full border border-solid border-[#c9e9dd] bg-brand-soft text-xs text-brand-strong">
                  {event.sequence}
                </span>
                <div className="grid gap-0.5 border-b border-solid border-[#edf3f0] pb-3">
                  <strong className="text-sm">{event.event_type}</strong>
                  <span className="text-sm text-text-muted">
                    {event.agent_name ?? "RetailPilot runtime"} · {formatDate(event.created_at)}
                  </span>
                </div>
              </li>
            ))}
          </ol>
        </Card>
      )}
      {!runQuery.data && !runQuery.isLoading && !runQuery.isError && (
        <Empty
          title="还没有查看任何运行"
          description="输入当前 owner 的 opaque run/trace selector 开始查看。"
        />
      )}
    </section>
  );
}
