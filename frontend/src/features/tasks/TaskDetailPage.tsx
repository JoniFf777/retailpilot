import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { useEffect, useRef, useState } from "react";
import { shopMindApi } from "../../api/client";
import { ApiError } from "../../api/errors";
import { useSession } from "../../app/useSession";
import type { TaskStepView } from "../../api/contracts";
import { Button, Card } from "../../components/primitives";
import {
  ERROR_STATE,
  EYEBROW,
  LOADING_PANEL,
  PAGE_HEADING,
  PAGE_LEDE,
  SECTION_HEADING,
  TEXT_BUTTON,
} from "../../components/textPatterns";
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

const ARTIFACT_ROW = "grid gap-0.5 border-t border-solid border-border pt-3";

const STEP_DOT_TONE: Record<string, string> = {
  completed: "bg-success",
  running: "bg-warning",
  failed: "bg-danger",
};

function stepDotTone(status: string): string {
  return STEP_DOT_TONE[status] ?? "bg-text-subtle";
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
  if (query.isLoading)
    return (
      <div className={LOADING_PANEL} role="status">
        正在加载任务快照…
      </div>
    );
  if (query.isError || !query.data)
    return (
      <div className={ERROR_STATE} role="alert">
        任务不存在或当前 owner 无权读取。
        <Link className={TEXT_BUTTON} to="/tasks">
          返回任务列表
        </Link>
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
    <section className="grid gap-8" aria-labelledby="task-detail-title">
      <Link className={TEXT_BUTTON} to="/tasks">
        ← 返回任务列表
      </Link>
      <div className={PAGE_HEADING}>
        <div>
          <p className={EYEBROW}>
            {task.mode.toUpperCase()} · {task.status}
          </p>
          <h1 id="task-detail-title">{task.goal.goal_text}</h1>
          <p className={PAGE_LEDE}>
            任务 {task.task_id} · 版本 {task.version} · 事件游标 {task.last_sequence}
          </p>
        </div>
        <Button
          disabled={
            cancel.isPending ||
            ["succeeded", "failed", "cancelled", "expired"].includes(task.status)
          }
          onClick={() => cancel.mutate()}
          variant="secondary"
        >
          取消任务
        </Button>
      </div>
      <div className="grid grid-cols-2 gap-5 max-[760px]:grid-cols-1">
        <Card as="article" className="grid gap-4">
          <div className={SECTION_HEADING}>
            <h2 className="m-0 text-xl">计划与步骤</h2>
            <span className="text-sm text-text-muted">{task.plan?.steps.length ?? 0} 步</span>
          </div>
          {task.plan && task.plan.steps.length > 0 && (
            <TaskDagView plan={task.plan} steps={steps} />
          )}
          {steps.map((step) => (
            // `task.steps` mixes every plan revision's steps together; a local repair
            // (revise_task_plan) can reuse the same step key in a later revision, so
            // the key must include plan_revision to stay unique across revisions.
            <div
              className="grid grid-cols-[auto_1fr_auto] items-center gap-3 border-t border-solid border-border py-3"
              key={`${step.plan_revision}:${step.key}`}
            >
              <span className={`h-3 w-3 rounded-full ${stepDotTone(step.status)}`} />
              <div className="grid gap-0.5">
                <strong>{step.key}</strong>
                <span className="text-sm text-text-muted">
                  {step.role} · {step.capability}
                </span>
              </div>
              <div className="grid justify-items-end gap-0.5">
                <em className="text-sm text-text-muted not-italic">{step.status}</em>
                {leaseLabel(step) && (
                  <small className="text-xs text-text-subtle">{leaseLabel(step)}</small>
                )}
              </div>
            </div>
          ))}
        </Card>
        <Card as="article" className="grid gap-4">
          <div className={SECTION_HEADING}>
            <h2 className="m-0 text-xl">结果与证据</h2>
            <span className="text-sm text-text-muted">{artifacts.length} 份产物</span>
          </div>
          {bundle?.options?.map((option, index) => (
            <div className={ARTIFACT_ROW} key={index}>
              <strong>
                方案 {index + 1} · {option.total} {option.currency}
              </strong>
              {option.items?.map((item) => (
                <span className="text-sm text-text-muted" key={`${item.slot}-${item.sku_code}`}>
                  {item.slot}: {item.sku_code} · {item.price}
                </span>
              ))}
            </div>
          ))}
          {verification?.issues?.map((issue, index) => (
            <div className={ARTIFACT_ROW} key={`${issue.code}-${index}`}>
              <strong>{issue.code}</strong>
              <span className="text-sm text-text-muted">{issue.message}</span>
            </div>
          ))}
          {task.output && !bundle ? (
            <pre className="max-h-[360px] overflow-auto rounded-sm border border-solid border-[#dcefe7] bg-[#f6fbf8] p-3.5 text-xs whitespace-pre-wrap">
              {JSON.stringify(task.output, null, 2)}
            </pre>
          ) : null}
          {artifacts.map((artifact) => (
            <div className={ARTIFACT_ROW} key={artifact.id}>
              <strong>{artifact.kind}</strong>
              <span className="text-sm text-text-muted">
                {artifact.branch} · {artifact.status}
              </span>
            </div>
          ))}
        </Card>
      </div>
      <RevisionHistory activeRevision={task.plan?.revision ?? 1} steps={steps} />
      {currentActionType && task.status === "succeeded" && !preparedAction && (
        <Button
          disabled={prepare.isPending}
          onClick={() => prepare.mutate()}
          className="justify-self-start"
        >
          准备确认动作
        </Button>
      )}
      {preparedAction && (
        <Card as="div" className="grid gap-4">
          <h2 className="m-0 text-xl">
            {preparedAction.action_type === "add_bundle_to_cart"
              ? "确认组合加购"
              : "确认保存本地草稿"}
          </h2>
          <Button
            disabled={confirm.isPending}
            onClick={() => confirm.mutate()}
            className="justify-self-start"
          >
            明确确认
          </Button>
        </Card>
      )}
      {task.status === "waiting_input" && (
        <Card
          as="form"
          className="grid max-w-[760px] gap-4"
          onSubmit={(event) => {
            event.preventDefault();
            if (feedback.trim()) sendFeedback.mutate();
          }}
        >
          <h2 className="m-0 text-xl">补充用户观察</h2>
          <textarea
            aria-label="用户补充事实"
            className="rounded-sm border border-solid border-border-strong p-3"
            rows={3}
            value={feedback}
            onChange={(event) => setFeedback(event.target.value)}
            placeholder="只记录你观察到的事实，不会被标记成系统已验证事实。"
          />
          <Button
            disabled={!feedback.trim() || sendFeedback.isPending}
            type="submit"
            className="justify-self-start"
          >
            提交补充
          </Button>
        </Card>
      )}
    </section>
  );
}
