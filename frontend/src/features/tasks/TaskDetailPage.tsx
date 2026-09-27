import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { useEffect, useRef, useState } from "react";
import { shopMindApi } from "../../api/client";
import { ApiError } from "../../api/errors";
import { useSession } from "../../app/useSession";
import type { TaskStepView } from "../../api/contracts";
import { RevisionHistory } from "./RevisionHistory";
import { TaskDagView } from "./TaskDagView";

function commandKey(taskId: string, operation: string): string {
  const storageKey = `shopmind:task-command:${taskId}:${operation}`;
  const existing = sessionStorage.getItem(storageKey);
  if (existing) return existing;
  const created = crypto.randomUUID();
  sessionStorage.setItem(storageKey, created);
  return created;
}

function clearCommandKey(taskId: string, operation: string): void {
  sessionStorage.removeItem(`shopmind:task-command:${taskId}:${operation}`);
}

/** `has_lease` only means the step is still holding a fencing token — it may already be
 *  stale, so this cross-checks `lease_until` rather than treating `has_lease` alone as
 *  "currently running" (see docs/frontend_redesign_handoff.md §7 point 4). */
function leaseLabel(step: TaskStepView): string | null {
  if (!step.has_lease) return null;
  if (!step.lease_until) return "持有租约";
  const until = new Date(step.lease_until);
  if (Number.isNaN(until.getTime()) || until.getTime() <= Date.now()) return "租约已过期";
  return `租约至 ${until.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}`;
}

export function TaskDetailPage() {
  const { taskId = "" } = useParams();
  const { userId } = useSession();
  const queryClient = useQueryClient();
  const [feedback, setFeedback] = useState("");
  const [preparedAction, setPreparedAction] = useState<{
    action_id: string;
    version: number;
    action_type: string;
  } | null>(null);
  const latestSequence = useRef(0);
  const query = useQuery({
    queryKey: ["shopping-task", taskId, userId],
    queryFn: () => shopMindApi.getShoppingTask(taskId, userId),
    enabled: Boolean(taskId && userId),
    refetchInterval: (data) =>
      data.state.data?.status === "queued" || data.state.data?.status === "running" ? 1000 : false,
  });
  useEffect(() => {
    latestSequence.current = Math.max(latestSequence.current, query.data?.last_sequence ?? 0);
  }, [query.data?.last_sequence]);
  useEffect(() => {
    if (
      !taskId ||
      !userId ||
      ["succeeded", "failed", "cancelled", "expired"].includes(query.data?.status ?? "")
    )
      return;
    let stopped = false;
    let retry: ReturnType<typeof setTimeout> | undefined;
    const connect = async () => {
      try {
        const events = await shopMindApi.streamShoppingTaskEvents(
          taskId,
          userId,
          latestSequence.current,
        );
        if (stopped) return;
        for (const event of events)
          latestSequence.current = Math.max(latestSequence.current, event.sequence);
        if (events.length)
          await queryClient.invalidateQueries({ queryKey: ["shopping-task", taskId, userId] });
      } catch (error) {
        if (error instanceof ApiError && error.status === 410) {
          latestSequence.current = 0;
          await queryClient.invalidateQueries({ queryKey: ["shopping-task", taskId, userId] });
        }
      }
      if (!stopped) retry = setTimeout(() => void connect(), 750);
    };
    void connect();
    return () => {
      stopped = true;
      if (retry) clearTimeout(retry);
    };
  }, [query.data?.status, queryClient, taskId, userId]);
  const refreshOnConflict = (error: unknown) => {
    if (error instanceof ApiError && error.status === 409)
      void queryClient.invalidateQueries({ queryKey: ["shopping-task", taskId, userId] });
  };
  const cancel = useMutation({
    mutationFn: () =>
      shopMindApi.cancelShoppingTask(
        taskId,
        { user_id: userId, expected_version: query.data?.version ?? 1 },
        commandKey(taskId, "cancel"),
      ),
    onSuccess: () => {
      clearCommandKey(taskId, "cancel");
      void queryClient.invalidateQueries({ queryKey: ["shopping-task", taskId, userId] });
    },
    onError: refreshOnConflict,
  });
  const sendFeedback = useMutation({
    mutationFn: () =>
      shopMindApi.addShoppingTaskInputs(
        taskId,
        {
          user_id: userId,
          expected_version: query.data?.version ?? 1,
          feedback: { observation: feedback, source: "user_reported" },
        },
        commandKey(taskId, "inputs"),
      ),
    onSuccess: () => {
      clearCommandKey(taskId, "inputs");
      setFeedback("");
      void queryClient.invalidateQueries({ queryKey: ["shopping-task", taskId, userId] });
    },
    onError: refreshOnConflict,
  });
  const currentActionType =
    query.data?.kind === "bundle_selection"
      ? "add_bundle_to_cart"
      : query.data?.kind === "after_sales_assessment"
        ? "save_after_sales_draft"
        : null;
  const prepare = useMutation({
    mutationFn: () =>
      shopMindApi.prepareShoppingTaskAction(
        taskId,
        {
          user_id: userId,
          expected_version: query.data?.version ?? 1,
          action_type: currentActionType!,
        },
        commandKey(taskId, "prepare-action"),
      ),
    onSuccess: (value) => {
      clearCommandKey(taskId, "prepare-action");
      setPreparedAction({
        action_id: value.action_id,
        version: value.version,
        action_type: value.action_type,
      });
    },
    onError: refreshOnConflict,
  });
  const confirm = useMutation({
    mutationFn: () =>
      shopMindApi.confirmShoppingTaskAction(
        taskId,
        preparedAction!.action_id,
        { user_id: userId, expected_version: preparedAction!.version, confirmed: true },
        commandKey(taskId, `confirm:${preparedAction!.action_id}`),
      ),
    onSuccess: () => {
      clearCommandKey(taskId, `confirm:${preparedAction!.action_id}`);
      setPreparedAction(null);
      void queryClient.invalidateQueries({ queryKey: ["shopping-task", taskId, userId] });
    },
    onError: refreshOnConflict,
  });
  if (query.isLoading) return <div className="loading-panel">正在加载任务快照…</div>;
  if (query.isError || !query.data)
    return (
      <div className="error-state standalone" role="alert">
        任务不存在或当前 owner 无权读取。<Link to="/tasks">返回任务列表</Link>
      </div>
    );
  const task = query.data;
  // steps/artifacts default to [] server-side (repository.snapshot()), but a default
  // isn't a JSON Schema "required" field, so the generated type still allows undefined.
  const steps = task.steps ?? [];
  const artifacts = task.artifacts ?? [];
  const bundle = task.output?.bundle_proposal;
  const verification = task.output?.verification_report;
  return (
    <section className="task-detail-page" aria-labelledby="task-detail-title">
      <Link className="text-button" to="/tasks">
        ← 返回任务列表
      </Link>
      <div className="page-heading">
        <div>
          <p className="eyebrow">
            {task.mode.toUpperCase()} · {task.status}
          </p>
          <h1 id="task-detail-title">{task.goal.goal_text}</h1>
          <p>
            任务 {task.task_id} · 版本 {task.version} · 事件游标 {task.last_sequence}
          </p>
        </div>
        <button
          className="secondary-button"
          disabled={
            cancel.isPending ||
            ["succeeded", "failed", "cancelled", "expired"].includes(task.status)
          }
          onClick={() => cancel.mutate()}
          type="button"
        >
          取消任务
        </button>
      </div>
      <div className="task-detail-grid">
        <article className="task-panel">
          <div className="section-heading">
            <h2>计划与步骤</h2>
            <span>{task.plan?.steps.length ?? 0} 步</span>
          </div>
          {task.plan && task.plan.steps.length > 0 && (
            <TaskDagView plan={task.plan} steps={steps} />
          )}
          {steps.map((step) => (
            // `task.steps` mixes every plan revision's steps together; a local repair
            // (revise_task_plan) can reuse the same step key in a later revision, so
            // the key must include plan_revision to stay unique across revisions.
            <div className="task-step-row" key={`${step.plan_revision}:${step.key}`}>
              <span className={`task-step-dot task-step-${step.status}`} />
              <div>
                <strong>{step.key}</strong>
                <span>
                  {step.role} · {step.capability}
                </span>
              </div>
              <div className="task-step-status">
                <em>{step.status}</em>
                {leaseLabel(step) && <small className="task-step-lease">{leaseLabel(step)}</small>}
              </div>
            </div>
          ))}
        </article>
        <article className="task-panel">
          <div className="section-heading">
            <h2>结果与证据</h2>
            <span>{artifacts.length} 份产物</span>
          </div>
          {bundle?.options?.map((option, index) => (
            <div className="task-artifact" key={index}>
              <strong>
                方案 {index + 1} · {option.total} {option.currency}
              </strong>
              {option.items?.map((item) => (
                <span key={`${item.slot}-${item.sku_code}`}>
                  {item.slot}: {item.sku_code} · {item.price}
                </span>
              ))}
            </div>
          ))}
          {verification?.issues?.map((issue, index) => (
            <div className="task-artifact" key={`${issue.code}-${index}`}>
              <strong>{issue.code}</strong>
              <span>{issue.message}</span>
            </div>
          ))}
          {task.output && !bundle ? (
            <pre className="task-output">{JSON.stringify(task.output, null, 2)}</pre>
          ) : null}
          {artifacts.map((artifact) => (
            <div className="task-artifact" key={artifact.id}>
              <strong>{artifact.kind}</strong>
              <span>
                {artifact.branch} · {artifact.status}
              </span>
            </div>
          ))}
        </article>
      </div>
      <RevisionHistory activeRevision={task.plan?.revision ?? 1} steps={steps} />
      {currentActionType && task.status === "succeeded" && !preparedAction && (
        <button
          className="primary-button"
          disabled={prepare.isPending}
          onClick={() => prepare.mutate()}
          type="button"
        >
          准备确认动作
        </button>
      )}
      {preparedAction && (
        <div className="task-panel">
          <h2>
            {preparedAction.action_type === "add_bundle_to_cart"
              ? "确认组合加购"
              : "确认保存本地草稿"}
          </h2>
          <button
            className="primary-button"
            disabled={confirm.isPending}
            onClick={() => confirm.mutate()}
            type="button"
          >
            明确确认
          </button>
        </div>
      )}
      {task.status === "waiting_input" && (
        <form
          className="task-panel task-feedback"
          onSubmit={(event) => {
            event.preventDefault();
            if (feedback.trim()) sendFeedback.mutate();
          }}
        >
          <h2>补充用户观察</h2>
          <textarea
            aria-label="用户补充事实"
            rows={3}
            value={feedback}
            onChange={(event) => setFeedback(event.target.value)}
            placeholder="只记录你观察到的事实，不会被标记成系统已验证事实。"
          />
          <button
            className="primary-button"
            disabled={!feedback.trim() || sendFeedback.isPending}
            type="submit"
          >
            提交补充
          </button>
        </form>
      )}
    </section>
  );
}
