import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { useState } from "react";
import { shopMindApi } from "../../api/client";
import { useSession } from "../../app/useSession";
import type { TaskKind } from "./taskTypes";

const labels: Record<TaskKind, string> = { bundle_selection: "组合选购", compatibility_diagnosis: "兼容排查", after_sales_assessment: "售后资格" };

export function TasksPage() {
  const { userId } = useSession();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [kind, setKind] = useState<TaskKind>("bundle_selection");
  const [goal, setGoal] = useState("我想为办公场景选择笔记本、显示器和扩展坞");
  const listQuery = useQuery({ queryKey: ["shopping-tasks", userId], queryFn: () => shopMindApi.listShoppingTasks(userId), enabled: Boolean(userId) });
  const create = useMutation({ mutationFn: () => shopMindApi.createShoppingTask({ user_id: userId, kind, goal_text: goal }), onSuccess: (result) => { void queryClient.invalidateQueries({ queryKey: ["shopping-tasks", userId] }); navigate(`/tasks/${result.task_id}`); } });
  return <section className="tasks-page" aria-labelledby="tasks-title">
    <div className="page-heading"><div><p className="eyebrow">DURABLE TASK WORKBENCH</p><h1 id="tasks-title">任务工作台</h1><p>把目标、计划、证据和确认动作保存在任务中；页面刷新不会把已验证产物变成一段不可追踪的聊天文本。</p></div></div>
    <div className="task-create-card"><div><p className="eyebrow">NEW TASK</p><h2>创建一个有边界的购物任务</h2></div><label className="field-label">任务类型<select value={kind} onChange={(event) => setKind(event.target.value as TaskKind)}><option value="bundle_selection">组合选购</option><option value="compatibility_diagnosis">兼容排查</option><option value="after_sales_assessment">售后资格分析</option></select></label><label className="field-label">目标<textarea rows={3} value={goal} onChange={(event) => setGoal(event.target.value)} /></label><button className="primary-button" disabled={!goal.trim() || create.isPending} onClick={() => create.mutate()} type="button">{create.isPending ? "提交中…" : "创建任务"}</button>{create.isError && <p className="task-error">任务创建失败，请检查数据库和 worker 状态。</p>}</div>
    <div className="task-list-card"><div className="section-heading"><div><p className="eyebrow">YOUR TASKS</p><h2>最近任务</h2></div><span>{listQuery.data?.items.length ?? 0} 项</span></div>{listQuery.isLoading && <div className="loading-panel">正在读取任务…</div>}{listQuery.data?.items.map((item) => <Link className="task-list-row" key={item.task_id} to={`/tasks/${item.task_id}`}><span className="task-kind">{labels[item.kind]}</span><strong>{item.task_id.slice(0, 8)}</strong><span>{item.status}</span><span>{item.mode}</span></Link>)}{!listQuery.isLoading && !listQuery.data?.items.length && <div className="empty-panel">还没有任务。先创建一个离线任务开始演示。</div>}</div>
  </section>;
}
