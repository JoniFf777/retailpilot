import { useQuery, useQueryClient } from "@tanstack/react-query";
import { chatErrorMessage } from "../chat/chatErrors";
import { shopMindApi } from "../../api/client";

interface ReadinessReport {
  profile: string;
  status: string;
  passed_checks: number;
  total_checks: number;
  failed_checks: number;
  checks: Array<{ check_id: string; status: string; reason: string }>;
}

function readHealth(value: unknown): { status: string } {
  return value && typeof value === "object" && "status" in value && typeof value.status === "string" ? { status: value.status } : { status: "unknown" };
}

function readReadiness(value: unknown): ReadinessReport {
  const report = value && typeof value === "object" ? value as Record<string, unknown> : {};
  const checks = Array.isArray(report.checks) ? report.checks.flatMap((check) => check && typeof check === "object" && typeof (check as Record<string, unknown>).check_id === "string" && typeof (check as Record<string, unknown>).status === "string" && typeof (check as Record<string, unknown>).reason === "string" ? [{ check_id: String((check as Record<string, unknown>).check_id), status: String((check as Record<string, unknown>).status), reason: String((check as Record<string, unknown>).reason) }] : []) : [];
  return { profile: typeof report.profile === "string" ? report.profile : "unknown", status: typeof report.status === "string" ? report.status : "unknown", passed_checks: typeof report.passed_checks === "number" ? report.passed_checks : 0, total_checks: typeof report.total_checks === "number" ? report.total_checks : 0, failed_checks: typeof report.failed_checks === "number" ? report.failed_checks : 0, checks };
}

function StatusBadge({ status }: { status: string }) {
  const tone = status === "ok" || status === "ready" || status === "passed" ? "status-good" : status === "blocked" || status === "failed" ? "status-bad" : "status-neutral";
  return <span className={`status-badge ${tone}`}>{status}</span>;
}

export function StatusPage() {
  const queryClient = useQueryClient();
  const health = useQuery({ queryKey: ["health"], queryFn: async ({ signal }) => readHealth(await shopMindApi.health(signal)) });
  const readiness = useQuery({ queryKey: ["readiness"], queryFn: async ({ signal }) => readReadiness(await shopMindApi.readiness(signal)) });
  const isLoading = health.isPending || readiness.isPending;
  const hasError = health.isError || readiness.isError;

  return (
    <section className="status-page" aria-labelledby="status-title">
      <div className="page-heading">
        <div>
          <p className="eyebrow">OPERATIONS</p>
          <h1 id="status-title">服务状态</h1>
          <p className="page-lede">只展示后端公开的健康与 readiness 状态，不展示连接串、密钥或原始错误。</p>
        </div>
        <button className="button secondary" type="button" onClick={() => { void queryClient.invalidateQueries({ queryKey: ["health"] }); void queryClient.invalidateQueries({ queryKey: ["readiness"] }); }}>重新检查</button>
      </div>

      {isLoading && <p className="state-card" role="status">正在检查服务状态…</p>}
      {hasError && <div className="state-card error-state" role="alert"><strong>状态检查失败</strong><span>{chatErrorMessage(health.error ?? readiness.error)}</span><button className="button secondary" type="button" onClick={() => { void health.refetch(); void readiness.refetch(); }}>重试</button></div>}

      {!isLoading && !hasError && health.data && readiness.data && (
        <>
          <div className="status-summary-grid">
            <article className="status-card"><span className="card-kicker">LIVENESS</span><div className="status-card-title"><h2>服务存活</h2><StatusBadge status={health.data.status} /></div><p>基础健康端点可访问。</p></article>
            <article className="status-card"><span className="card-kicker">READINESS</span><div className="status-card-title"><h2>部署就绪</h2><StatusBadge status={readiness.data.status} /></div><p>{readiness.data.passed_checks}/{readiness.data.total_checks} 项检查通过，{readiness.data.failed_checks} 项失败。</p></article>
          </div>
          <div className="status-detail-card"><div className="section-heading"><div><span className="card-kicker">CLOSED CHECKS</span><h2>Readiness 检查</h2></div><span className="muted">profile: {readiness.data.profile}</span></div><ul className="status-check-list">{readiness.data.checks.map((check) => <li key={check.check_id}><span><strong>{check.check_id}</strong><small>{check.reason}</small></span><StatusBadge status={check.status} /></li>)}</ul></div>
        </>
      )}
    </section>
  );
}
