import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { useState } from "react";
import { shopMindApi } from "../../api/client";
import { useSession } from "../../app/useSession";
import type { TaskKind } from "../../api/contracts";
import { Button, Card, Empty } from "../../components/primitives";
import {
  EYEBROW,
  FIELD_LABEL,
  LOADING_PANEL,
  PAGE_HEADING,
  PAGE_LEDE,
  SECTION_HEADING,
} from "../../components/textPatterns";

const labels: Record<TaskKind, string> = {
  bundle_selection: "组合选购",
  compatibility_diagnosis: "兼容排查",
  after_sales_assessment: "售后资格",
};

const SELECT_INPUT =
  "rounded-sm border border-solid border-border-strong bg-surface px-3 py-2.5 text-sm text-text-primary";

export function TasksPage() {
  const { userId } = useSession();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [kind, setKind] = useState<TaskKind>("bundle_selection");
  const [goal, setGoal] = useState("我想为办公场景选择笔记本、显示器和扩展坞");
  const listQuery = useQuery({
    queryKey: ["shopping-tasks", userId],
    queryFn: () => shopMindApi.listShoppingTasks(userId),
    enabled: Boolean(userId),
  });
  const create = useMutation({
    mutationFn: () => shopMindApi.createShoppingTask({ user_id: userId, kind, goal_text: goal }),
    onSuccess: (result) => {
      void queryClient.invalidateQueries({ queryKey: ["shopping-tasks", userId] });
      navigate(`/tasks/${result.task_id}`);
    },
  });
  return (
    <section className="grid gap-8" aria-labelledby="tasks-title">
      <div className={PAGE_HEADING}>
        <div>
          <p className={EYEBROW}>DURABLE TASK WORKBENCH</p>
          <h1 id="tasks-title">任务工作台</h1>
          <p className={PAGE_LEDE}>
            把目标、计划、证据和确认动作保存在任务中；页面刷新不会把已验证产物变成一段不可追踪的聊天文本。
          </p>
        </div>
      </div>
      <Card as="div" className="grid max-w-[760px] gap-4">
        <div>
          <p className={EYEBROW}>NEW TASK</p>
          <h2 className="m-0 text-xl">创建一个有边界的购物任务</h2>
        </div>
        <label className={FIELD_LABEL}>
          任务类型
          <select
            className={SELECT_INPUT}
            value={kind}
            onChange={(event) => setKind(event.target.value as TaskKind)}
          >
            <option value="bundle_selection">组合选购</option>
            <option value="compatibility_diagnosis">兼容排查</option>
            <option value="after_sales_assessment">售后资格分析</option>
          </select>
        </label>
        <label className={FIELD_LABEL}>
          目标
          <textarea
            className={SELECT_INPUT}
            rows={3}
            value={goal}
            onChange={(event) => setGoal(event.target.value)}
          />
        </label>
        <Button disabled={!goal.trim() || create.isPending} onClick={() => create.mutate()}>
          {create.isPending ? "提交中…" : "创建任务"}
        </Button>
        {create.isError && (
          <p className="m-0 text-sm text-danger">任务创建失败，请检查数据库和 worker 状态。</p>
        )}
      </Card>
      <Card as="div" className="grid gap-2">
        <div className={SECTION_HEADING}>
          <div>
            <p className={EYEBROW}>YOUR TASKS</p>
            <h2 className="m-0 text-xl">最近任务</h2>
          </div>
          <span className="text-sm text-text-muted">{listQuery.data?.items.length ?? 0} 项</span>
        </div>
        {listQuery.isLoading && (
          <div className={LOADING_PANEL} role="status">
            正在读取任务…
          </div>
        )}
        {listQuery.data?.items.map((item) => (
          <Link
            className="grid grid-cols-[minmax(120px,1fr)_minmax(80px,0.7fr)_1fr_1fr] items-center gap-3 border-t border-solid border-border py-3.5 text-inherit no-underline hover:bg-surface-soft max-sm:grid-cols-2"
            key={item.task_id}
            to={`/tasks/${item.task_id}`}
          >
            <span className="font-extrabold text-brand-strong">{labels[item.kind]}</span>
            <strong>{item.task_id.slice(0, 8)}</strong>
            <span>{item.status}</span>
            <span>{item.mode}</span>
          </Link>
        ))}
        {!listQuery.isLoading && !listQuery.data?.items.length && (
          <Empty title="还没有任务。先创建一个离线任务开始演示。" />
        )}
      </Card>
    </section>
  );
}
