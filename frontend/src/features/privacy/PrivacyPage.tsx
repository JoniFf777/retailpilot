import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Badge, Button, Card, Empty, Field, type BadgeTone } from "../../components/primitives";
import { EYEBROW, PAGE_HEADING, PAGE_LEDE, SECTION_HEADING } from "../../components/textPatterns";
import { shopMindApi } from "../../api/client";
import type { OwnerMemoryRecord } from "../../api/contracts";
import { useSession } from "../../app/useSession";
import { chatErrorMessage } from "../chat/chatErrors";

const DELETE_PHRASE = "删除我的全部 RetailPilot 数据";

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(
    new Date(value),
  );
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

function memoryStatusTone(status: string): BadgeTone {
  if (status === "active") return "success";
  if (status === "deleted") return "danger";
  return "neutral";
}

function MemoryCard({
  memory,
  draft,
  deleteTarget,
  busy,
  onDraftChange,
  onCorrect,
  onDelete,
}: {
  memory: OwnerMemoryRecord;
  draft: string;
  deleteTarget: string | null;
  busy: boolean;
  onDraftChange: (value: string) => void;
  onCorrect: () => void;
  onDelete: () => void;
}) {
  return (
    <Card as="article" className="grid gap-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <span className="text-xs text-text-subtle">
            {memory.kind} · {memory.scope}
          </span>
          <h3 className="mt-1 mb-0 text-sm">{memory.memory_id}</h3>
        </div>
        <Badge tone={memoryStatusTone(memory.status)}>{memory.status}</Badge>
      </div>
      <p className="m-0 text-xs text-text-subtle">
        创建于 {formatDate(memory.created_at)} · 更新于 {formatDate(memory.updated_at)}
      </p>
      <Field htmlFor={`memory-content-${memory.memory_id}`} label="Memory 内容">
        <textarea
          className="min-h-18 rounded-sm border border-border-strong p-3"
          data-testid={`memory-content-${memory.memory_id}`}
          id={`memory-content-${memory.memory_id}`}
          onChange={(event) => onDraftChange(event.target.value)}
          value={draft}
        />
      </Field>
      <div className="flex justify-end gap-2.5">
        <Button
          data-testid={`memory-correct-${memory.memory_id}`}
          disabled={busy || !draft.trim()}
          onClick={onCorrect}
          size="sm"
          variant="secondary"
        >
          保存纠正
        </Button>
        <Button
          data-testid={`memory-delete-${memory.memory_id}`}
          disabled={busy}
          onClick={onDelete}
          size="sm"
          variant="danger"
        >
          {deleteTarget === memory.memory_id ? "确认删除" : "删除 Memory"}
        </Button>
      </div>
    </Card>
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
  const invalidateInventory = () =>
    queryClient.invalidateQueries({ queryKey: ["owner-data", effectiveOwner] });
  const correctMutation = useMutation({
    mutationFn: ({ memoryId, content }: { memoryId: string; content: string }) =>
      shopMindApi.correctMemory({ user_id: effectiveOwner, memory_id: memoryId, content }),
    onSuccess: () => {
      setActionError(null);
      void invalidateInventory();
    },
    onError: (error) => setActionError(chatErrorMessage(error)),
  });
  const deleteMemoryMutation = useMutation({
    mutationFn: (memoryId: string) =>
      shopMindApi.deleteMemory({ user_id: effectiveOwner, memory_id: memoryId }),
    onSuccess: () => {
      setDeleteTarget(null);
      setActionError(null);
      void invalidateInventory();
    },
    onError: (error) => setActionError(chatErrorMessage(error)),
  });
  const deleteAllMutation = useMutation({
    mutationFn: () =>
      shopMindApi.deleteOwnerData({
        user_id: effectiveOwner,
        deletion_request_id: crypto.randomUUID(),
        confirmed: true,
      }),
    onSuccess: () => {
      setDeletePhrase("");
      setActionError(null);
      void invalidateInventory();
    },
    onError: (error) => setActionError(chatErrorMessage(error)),
  });

  const busy =
    correctMutation.isPending || deleteMemoryMutation.isPending || deleteAllMutation.isPending;
  const counts = useMemo(
    () => (inventoryQuery.data ? Object.entries(inventoryQuery.data.counts) : []),
    [inventoryQuery.data],
  );

  return (
    <section aria-labelledby="privacy-title" className="grid gap-6">
      <div className={PAGE_HEADING}>
        <div>
          <p className={EYEBROW}>OWNER DATA BOUNDARY</p>
          <h1 id="privacy-title">隐私中心</h1>
          <p className={PAGE_LEDE}>
            查看、纠正或删除属于当前身份的 RetailPilot 数据。页面只显示后端允许的摘要字段。
          </p>
        </div>
      </div>
      {isDevelopment ? (
        <Card
          as="div"
          className="flex flex-wrap items-center gap-3 bg-surface/88 text-sm text-text-muted"
        >
          <label
            className="flex items-center gap-2 font-semibold text-text-primary"
            htmlFor="privacy-user-id"
          >
            开发用户标识
            <input
              className="w-45 rounded-sm border border-border-strong px-2.5 py-1.5 font-normal"
              id="privacy-user-id"
              onChange={(event) => setUserId(event.target.value)}
              value={userId}
            />
          </label>
          <span className="text-xs text-text-subtle">切换身份会清空前端 Query cache。</span>
        </Card>
      ) : (
        <Card as="div" className="text-sm text-text-muted">
          当前生产身份由可信入口提供；浏览器不会保存或构造身份签名。
        </Card>
      )}
      {!effectiveOwner && <Empty title="请输入开发用户标识后查看 owner-data。" />}
      {inventoryQuery.isLoading && (
        <p className="m-0 text-sm text-text-muted" role="status">
          正在读取当前 owner 的数据清单…
        </p>
      )}
      {inventoryQuery.isError && (
        <Card
          as="div"
          className="flex flex-wrap items-center justify-between gap-3 border-danger/25 bg-danger-soft"
          role="alert"
        >
          <div>
            <strong className="text-text-primary">无法读取 owner-data</strong>
            <p className="m-0 text-sm text-text-muted">{chatErrorMessage(inventoryQuery.error)}</p>
          </div>
          <Button onClick={() => void inventoryQuery.refetch()} size="sm" variant="secondary">
            重试
          </Button>
        </Card>
      )}
      {inventoryQuery.data && (
        <>
          <Card className="grid gap-4">
            <div className={SECTION_HEADING}>
              <div>
                <p className={EYEBROW}>INVENTORY</p>
                <h2>数据清单</h2>
              </div>
              <span className="text-xs text-text-subtle">
                {inventoryQuery.data.total_records} 条记录
              </span>
            </div>
            <div className="grid grid-cols-[repeat(auto-fit,minmax(120px,1fr))] gap-2.5">
              {counts.map(([key, count]) => (
                <div
                  className="grid gap-1 rounded-md border border-border bg-surface-soft p-3.5"
                  key={key}
                >
                  <strong className="text-2xl tracking-tight">{count}</strong>
                  <span className="text-xs text-text-muted">{COUNT_LABELS[key] ?? key}</span>
                </div>
              ))}
            </div>
          </Card>
          <Card className="grid gap-4">
            <div className={SECTION_HEADING}>
              <div>
                <p className={EYEBROW}>MEMORY</p>
                <h2>Memory</h2>
              </div>
              <span className="text-xs text-text-subtle">
                {inventoryQuery.data.memory_truncated
                  ? `仅显示前 ${inventoryQuery.data.memory_limit} 条`
                  : `${inventoryQuery.data.memories.length} 条`}
              </span>
            </div>
            {inventoryQuery.data.memories.length === 0 ? (
              <Empty title="当前没有可展示的 Memory。" />
            ) : (
              <div className="grid gap-3.5">
                {inventoryQuery.data.memories.map((memory) => (
                  <MemoryCard
                    busy={busy}
                    deleteTarget={deleteTarget}
                    draft={memoryDrafts[memory.memory_id] ?? memory.content}
                    key={memory.memory_id}
                    memory={memory}
                    onCorrect={() =>
                      correctMutation.mutate({
                        memoryId: memory.memory_id,
                        content: memoryDrafts[memory.memory_id] ?? memory.content,
                      })
                    }
                    onDelete={() => {
                      if (deleteTarget === memory.memory_id)
                        deleteMemoryMutation.mutate(memory.memory_id);
                      else setDeleteTarget(memory.memory_id);
                    }}
                    onDraftChange={(value) =>
                      setMemoryDrafts((current) => ({ ...current, [memory.memory_id]: value }))
                    }
                  />
                ))}
              </div>
            )}
          </Card>
          <Card className="grid gap-3 border-danger/25">
            <p className={EYEBROW}>IRREVERSIBLE</p>
            <h2 className="m-0 text-xl">删除全部个人数据</h2>
            <p className="m-0 max-w-[760px] text-sm leading-relaxed text-text-muted">
              这会删除当前 owner
              的会话、消息、Memory、待确认操作与运行记录；不会删除商品目录，也不会删除独立保留的治理审计指纹。
            </p>
            <Field htmlFor="delete-owner-data" label={`请输入确认短语：${DELETE_PHRASE}`}>
              <input
                className="rounded-sm border border-border-strong px-2.5 py-1.5"
                data-testid="delete-owner-data"
                id="delete-owner-data"
                onChange={(event) => setDeletePhrase(event.target.value)}
                value={deletePhrase}
              />
            </Field>
            <Button
              className="justify-self-start"
              data-testid="delete-owner-button"
              disabled={busy || deletePhrase !== DELETE_PHRASE}
              onClick={() => deleteAllMutation.mutate()}
              variant="danger"
            >
              确认删除全部数据
            </Button>
          </Card>
        </>
      )}
      {actionError && (
        <Card
          as="div"
          className="flex flex-wrap items-center justify-between gap-3 border-danger/25 bg-danger-soft"
          role="alert"
        >
          <div>
            <strong className="text-text-primary">操作未完成</strong>
            <p className="m-0 text-sm text-text-muted">{actionError}</p>
          </div>
          <Button onClick={() => setActionError(null)} size="sm" variant="secondary">
            关闭
          </Button>
        </Card>
      )}
    </section>
  );
}
