import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { shopMindApi } from "../../api/client";
import type { OwnerMemoryRecord } from "../../api/contracts";
import { useSession } from "../../app/useSession";
import { chatErrorMessage } from "../chat/chatErrors";

const DELETE_PHRASE = "删除我的全部 ShopMind 数据";

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

const COUNT_LABELS: Record<string, string> = {
  preferences: "偏好",
  cart_items: "购物车",
  pending_actions: "待确认操作",
  candidate_contexts: "候选上下文",
  conversation_threads: "会话",
  conversation_messages: "消息",
  agent_runs: "运行",
  agent_run_events: "运行事件",
  conversation_summaries: "会话摘要",
  idempotency_records: "幂等记录",
  memory_records: "Memory",
};

function MemoryCard({ memory, draft, deleteTarget, busy, onDraftChange, onCorrect, onDelete }: {
  memory: OwnerMemoryRecord;
  draft: string;
  deleteTarget: string | null;
  busy: boolean;
  onDraftChange: (value: string) => void;
  onCorrect: () => void;
  onDelete: () => void;
}) {
  return (
    <article className="memory-card">
      <div className="memory-card-heading"><div><span className="memory-kind">{memory.kind} · {memory.scope}</span><h3>{memory.memory_id}</h3></div><span className={`memory-status memory-status-${memory.status}`}>{memory.status}</span></div>
      <p className="memory-meta">创建于 {formatDate(memory.created_at)} · 更新于 {formatDate(memory.updated_at)}</p>
      <label className="field-label" htmlFor={`memory-content-${memory.memory_id}`}>Memory 内容<textarea data-testid={`memory-content-${memory.memory_id}`} id={`memory-content-${memory.memory_id}`} onChange={(event) => onDraftChange(event.target.value)} value={draft} /></label>
      <div className="memory-actions"><button className="secondary-button" data-testid={`memory-correct-${memory.memory_id}`} disabled={busy || !draft.trim()} onClick={onCorrect} type="button">保存纠正</button><button className="danger-button" data-testid={`memory-delete-${memory.memory_id}`} disabled={busy} onClick={onDelete} type="button">{deleteTarget === memory.memory_id ? "确认删除" : "删除 Memory"}</button></div>
    </article>
  );
}

export function PrivacyPage() {
  const { isDevelopment, userId, setUserId } = useSession();
  const effectiveOwner = isDevelopment ? userId.trim() : "";
  const queryClient = useQueryClient();
  const [memoryDrafts, setMemoryDrafts] = useState<Record<string, string>>({});
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const [deletePhrase, setDeletePhrase] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);

  const inventoryQuery = useQuery({
    queryKey: ["owner-data", effectiveOwner],
    queryFn: () => shopMindApi.inspectOwnerData(effectiveOwner),
    enabled: Boolean(effectiveOwner),
  });
  const invalidateInventory = () => queryClient.invalidateQueries({ queryKey: ["owner-data", effectiveOwner] });
  const correctMutation = useMutation({
    mutationFn: ({ memoryId, content }: { memoryId: string; content: string }) => shopMindApi.correctMemory({ user_id: effectiveOwner, memory_id: memoryId, content }),
    onSuccess: () => { setActionError(null); void invalidateInventory(); },
    onError: (error) => setActionError(chatErrorMessage(error)),
  });
  const deleteMemoryMutation = useMutation({
    mutationFn: (memoryId: string) => shopMindApi.deleteMemory({ user_id: effectiveOwner, memory_id: memoryId }),
    onSuccess: () => { setDeleteTarget(null); setActionError(null); void invalidateInventory(); },
    onError: (error) => setActionError(chatErrorMessage(error)),
  });
  const deleteAllMutation = useMutation({
    mutationFn: () => shopMindApi.deleteOwnerData({ user_id: effectiveOwner, deletion_request_id: crypto.randomUUID(), confirmed: true }),
    onSuccess: () => { setDeletePhrase(""); setActionError(null); void invalidateInventory(); },
    onError: (error) => setActionError(chatErrorMessage(error)),
  });

  const busy = correctMutation.isPending || deleteMemoryMutation.isPending || deleteAllMutation.isPending;
  const counts = useMemo(() => inventoryQuery.data ? Object.entries(inventoryQuery.data.counts) : [], [inventoryQuery.data]);

  return (
    <section className="privacy-page" aria-labelledby="privacy-title">
      <div className="page-heading"><div><p className="eyebrow">OWNER DATA BOUNDARY</p><h1 id="privacy-title">隐私中心</h1><p>查看、纠正或删除属于当前身份的 ShopMind 数据。页面只显示后端允许的摘要字段。</p></div></div>
      {isDevelopment ? <label className="identity-strip" htmlFor="privacy-user-id">开发用户标识<input id="privacy-user-id" value={userId} onChange={(event) => setUserId(event.target.value)} /><span>切换身份会清空前端 Query cache。</span></label> : <div className="notice-card">当前生产身份由可信入口提供；浏览器不会保存或构造身份签名。</div>}
      {!effectiveOwner && <div className="empty-panel">请输入开发用户标识后查看 owner-data。</div>}
      {inventoryQuery.isLoading && <div className="loading-panel" role="status">正在读取当前 owner 的数据清单…</div>}
      {inventoryQuery.isError && <div className="error-state standalone" role="alert"><div><strong>无法读取 owner-data</strong><p>{chatErrorMessage(inventoryQuery.error)}</p></div><button className="text-button" onClick={() => void inventoryQuery.refetch()} type="button">重试</button></div>}
      {inventoryQuery.data && <>
        <div className="privacy-section"><div className="section-heading"><div><p className="eyebrow">INVENTORY</p><h2>数据清单</h2></div><span>{inventoryQuery.data.total_records} 条记录</span></div><div className="count-grid">{counts.map(([key, count]) => <div className="count-card" key={key}><strong>{count}</strong><span>{COUNT_LABELS[key] ?? key}</span></div>)}</div></div>
        <div className="privacy-section"><div className="section-heading"><div><p className="eyebrow">MEMORY</p><h2>Memory</h2></div><span>{inventoryQuery.data.memory_truncated ? `仅显示前 ${inventoryQuery.data.memory_limit} 条` : `${inventoryQuery.data.memories.length} 条`}</span></div>{inventoryQuery.data.memories.length === 0 ? <div className="empty-panel">当前没有可展示的 Memory。</div> : <div className="memory-list">{inventoryQuery.data.memories.map((memory) => <MemoryCard busy={busy} deleteTarget={deleteTarget} draft={memoryDrafts[memory.memory_id] ?? memory.content} key={memory.memory_id} memory={memory} onCorrect={() => correctMutation.mutate({ memoryId: memory.memory_id, content: memoryDrafts[memory.memory_id] ?? memory.content })} onDelete={() => { if (deleteTarget === memory.memory_id) deleteMemoryMutation.mutate(memory.memory_id); else setDeleteTarget(memory.memory_id); }} onDraftChange={(value) => setMemoryDrafts((current) => ({ ...current, [memory.memory_id]: value }))} />)}</div>}</div>
        <div className="privacy-section destructive-section"><p className="eyebrow">IRREVERSIBLE</p><h2>删除全部个人数据</h2><p>这会删除当前 owner 的会话、消息、Memory、待确认操作与运行记录；不会删除商品目录，也不会删除独立保留的治理审计指纹。</p><label className="field-label" htmlFor="delete-owner-data">请输入确认短语：{DELETE_PHRASE}<input data-testid="delete-owner-data" id="delete-owner-data" onChange={(event) => setDeletePhrase(event.target.value)} value={deletePhrase} /></label><button className="danger-button" data-testid="delete-owner-button" disabled={busy || deletePhrase !== DELETE_PHRASE} onClick={() => deleteAllMutation.mutate()} type="button">确认删除全部数据</button></div>
      </>}
      {actionError && <div className="error-state standalone" role="alert"><div><strong>操作未完成</strong><p>{actionError}</p></div><button className="text-button" onClick={() => setActionError(null)} type="button">关闭</button></div>}
    </section>
  );
}
