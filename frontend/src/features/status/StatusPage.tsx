import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge, Button, Card, type BadgeTone } from "../../components/primitives";
import { EYEBROW, PAGE_HEADING, PAGE_LEDE, SECTION_HEADING } from "../../components/textPatterns";
import { chatErrorMessage } from "../chat/chatErrors";
import { shopMindApi } from "../../api/client";
import { useSystemReadiness } from "./useSystemReadiness";

function readHealth(value: unknown): { status: string } {
  return value && typeof value === "object" && "status" in value && typeof value.status === "string"
    ? { status: value.status }
    : { status: "unknown" };
}

function statusTone(status: string): BadgeTone {
  if (status === "ok" || status === "ready" || status === "passed") return "success";
  if (status === "blocked" || status === "failed") return "danger";
  return "neutral";
}

function StatusBadge({ status }: { status: string }) {
  return <Badge tone={statusTone(status)}>{status}</Badge>;
}

export function StatusPage() {
  const queryClient = useQueryClient();
  const health = useQuery({
    queryKey: ["health"],
    queryFn: async ({ signal }) => readHealth(await shopMindApi.health(signal)),
  });
  const readiness = useSystemReadiness();
  const isLoading = health.isPending || readiness.isPending;
  const hasError = health.isError || readiness.isError;

  return (
    <section aria-labelledby="status-title" className="grid gap-6">
      <div className={PAGE_HEADING}>
        <div>
          <p className={EYEBROW}>OPERATIONS</p>
          <h1 id="status-title">服务状态</h1>
          <p className={PAGE_LEDE}>
            只展示后端公开的健康与 readiness 状态，不展示连接串、密钥或原始错误。
          </p>
        </div>
        <Button
          onClick={() => {
            void queryClient.invalidateQueries({ queryKey: ["health"] });
            void queryClient.invalidateQueries({ queryKey: ["readiness"] });
          }}
          variant="secondary"
        >
          重新检查
        </Button>
      </div>

      {isLoading && (
        <p className="m-0 text-sm text-text-muted" role="status">
          正在检查服务状态…
        </p>
      )}
      {hasError && (
        <Card as="div" className="grid gap-2 border-danger/25 bg-danger-soft" role="alert">
          <strong className="text-text-primary">状态检查失败</strong>
          <span className="text-sm text-text-muted">
            {chatErrorMessage(health.error ?? readiness.error)}
          </span>
          <Button
            className="justify-self-start"
            onClick={() => {
              void health.refetch();
              void readiness.refetch();
            }}
            size="sm"
            variant="secondary"
          >
            重试
          </Button>
        </Card>
      )}

      {!isLoading && !hasError && health.data && readiness.data && (
        <>
          <div className="grid gap-4 sm:grid-cols-2">
            <Card as="article" className="grid gap-2">
              <span className="text-[0.66rem] font-extrabold tracking-wide text-text-subtle uppercase">
                LIVENESS
              </span>
              <div className="flex items-center justify-between gap-2">
                <h2 className="m-0 text-lg">服务存活</h2>
                <StatusBadge status={health.data.status} />
              </div>
              <p className="m-0 text-sm text-text-muted">基础健康端点可访问。</p>
            </Card>
            <Card as="article" className="grid gap-2">
              <span className="text-[0.66rem] font-extrabold tracking-wide text-text-subtle uppercase">
                READINESS
              </span>
              <div className="flex items-center justify-between gap-2">
                <h2 className="m-0 text-lg">部署就绪</h2>
                <StatusBadge status={readiness.data.status} />
              </div>
              <p className="m-0 text-sm text-text-muted">
                {readiness.data.passed_checks}/{readiness.data.total_checks} 项检查通过，
                {readiness.data.failed_checks} 项失败。
              </p>
            </Card>
          </div>
          <Card className="grid gap-4">
            <div className={SECTION_HEADING}>
              <div>
                <span className="text-[0.66rem] font-extrabold tracking-wide text-text-subtle uppercase">
                  CLOSED CHECKS
                </span>
                <h2>Readiness 检查</h2>
              </div>
              <span className="text-xs text-text-subtle">profile: {readiness.data.profile}</span>
            </div>
            <ul className="m-0 grid list-none gap-2.5 p-0">
              {readiness.data.checks.map((check) => (
                <li
                  className="flex items-center justify-between gap-3 border-t border-solid border-border pt-2.5 first:border-t-0 first:pt-0"
                  key={check.check_id}
                >
                  <span className="grid gap-0.5">
                    <strong className="text-sm">{check.check_id}</strong>
                    <small className="text-xs text-text-subtle">{check.reason}</small>
                  </span>
                  <StatusBadge status={check.status} />
                </li>
              ))}
            </ul>
          </Card>
        </>
      )}
    </section>
  );
}
