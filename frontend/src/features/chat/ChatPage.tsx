import type { FormEvent } from "react";
import { Link } from "react-router-dom";
import { ActionDrawer } from "../actions/ActionDrawer";
import { CartPanel } from "../cart/CartPanel";
import { AssistantMessage } from "./AssistantMessage";
import { ExecutionTimeline } from "./ExecutionTimeline";
import { MessageBubble } from "./MessageBubble";
import { useChatSession } from "./useChatSession";
import { cn } from "../../components/cn";
import { Button } from "../../components/primitives";
import { BUTTON_SECONDARY, ERROR_STATE, EYEBROW, TEXT_BUTTON } from "../../components/textPatterns";

const QUICK_PROMPTS = [
  "预算 6000 元以内，主要用于 Java 开发，内存至少 16GB，希望尽量轻",
  "预算 12000 元以内，想买适合开发和出差的轻薄笔记本",
  "TECH-LAP-001 多少钱？",
];

const TOGGLE_BUTTON =
  "min-h-9 cursor-pointer rounded-[0.45rem] border-0 bg-transparent px-2 text-xs text-text-muted";
const TOGGLE_BUTTON_SELECTED = "bg-surface font-extrabold text-brand-strong shadow-sm";
const SOFT_PANEL = "grid gap-2 rounded-md border border-border bg-surface-soft p-3.5";

export function ChatPage() {
  const {
    threadShortId,
    messages,
    draft,
    setDraft,
    error,
    transport,
    setTransport,
    streamState,
    streamBusy,
    busy,
    actionBusy,
    inputRef,
    isDevelopment,
    userId,
    setUserId,
    cartEnabled,
    actionSession,
    actionError,
    resolution,
    navigate,
    submitMessage,
    retryLastMessage,
    submitAction,
    startNewThread,
    cancelStream,
    fillDraft,
    selectSku,
    dismissAction,
  } = useChatSession();

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    submitMessage(draft);
  }

  return (
    <section className="grid gap-8" aria-labelledby="chat-title">
      <div className="flex flex-col items-start gap-5 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className={EYEBROW}>RETAILPILOT WORKBENCH</p>
          <h1 className="max-w-[720px]" id="chat-title">
            把购物问题，变成清晰决定
          </h1>
          <p className="mt-4 text-base leading-[1.7] text-text-muted">
            用中文描述需求，RetailPilot 会整理商品信息、偏好与决策依据。
          </p>
        </div>
        <div className="flex items-center gap-2.5">
          <Link className={BUTTON_SECONDARY} to="/tasks">
            进入持久任务
          </Link>
          <Button disabled={busy} onClick={startNewThread} variant="secondary">
            新建会话
          </Button>
        </div>
      </div>
      <div className="grid items-start gap-5 lg:grid-cols-[minmax(220px,0.34fr)_minmax(0,1fr)]">
        <aside
          className="order-2 grid gap-4 rounded-lg border border-border bg-surface/90 p-4 shadow-soft lg:order-none"
          aria-label="会话信息"
        >
          <div className="flex items-center justify-between px-0.5 py-1 text-[0.84rem] font-extrabold">
            <span>当前会话</span>
            <span className="inline-flex items-center gap-1 text-xs text-success">
              <span className="h-2.5 w-2.5 rounded-full border-[3px] border-success/25 bg-success" />
              在线
            </span>
          </div>
          <div className={SOFT_PANEL}>
            <span className="text-xs font-extrabold tracking-wide text-text-muted uppercase">
              Thread
            </span>
            <code className="overflow-hidden text-sm text-ellipsis text-brand-strong">
              {threadShortId}
            </code>
            <small className="text-xs leading-relaxed text-text-subtle">
              Action 只绑定当前 thread 和消息的 recommendation_context。
            </small>
          </div>
          {isDevelopment && (
            <label
              className="grid gap-1.5 text-xs font-extrabold tracking-wide text-text-muted uppercase"
              htmlFor="dev-user-id"
            >
              开发用户标识
              <input
                className="rounded-sm border border-border-strong bg-surface px-3 py-2.5 text-sm font-normal tracking-normal text-text-primary normal-case"
                id="dev-user-id"
                value={userId}
                onChange={(event) => setUserId(event.target.value)}
              />
            </label>
          )}
          <div className={SOFT_PANEL}>
            <span className="text-xs font-extrabold tracking-wide text-text-muted uppercase">
              安全边界
            </span>
            <p className="m-0 text-[0.77rem] leading-relaxed text-text-muted">
              商品选择进入结构化 PendingAction；确认和取消分别通过专用端点。
            </p>
          </div>
          <CartPanel enabled={cartEnabled} onCheckout={() => navigate("/checkout")} />
        </aside>
        <div className="grid min-h-[560px] overflow-hidden rounded-lg border border-border bg-surface/90 shadow-soft lg:min-h-[620px]">
          <div className="flex items-center justify-between border-b border-border px-5.5 py-4.5">
            <div>
              <strong className="block text-[0.95rem]">购物决策对话</strong>
              <span className="mt-1 block text-xs text-text-subtle">
                {transport === "stream" ? "Ordered POST-SSE" : "POST JSON"}
              </span>
            </div>
            <div className="flex items-center gap-3">
              {busy && (
                <span className="font-bold text-warning" role="status">
                  处理中…
                </span>
              )}
              {streamBusy && (
                <button className={TEXT_BUTTON} onClick={cancelStream} type="button">
                  停止接收
                </button>
              )}
            </div>
          </div>
          {streamState.progress.length > 0 && streamBusy && (
            <ExecutionTimeline
              progress={streamState.progress}
              lastSequence={streamState.lastSequence}
            />
          )}
          <div
            aria-live="polite"
            className="flex max-h-[520px] min-h-[300px] flex-1 flex-col gap-4 overflow-auto p-5.5"
            data-testid="message-list"
          >
            {messages.length === 0 ? (
              <div className="m-auto max-w-[410px] self-center py-10 text-center">
                <div
                  className="mb-3.5 inline-flex h-[3.35rem] w-[3.35rem] items-center justify-center rounded-2xl border border-brand/25 bg-brand-soft text-xl text-brand"
                  aria-hidden="true"
                >
                  ⌁
                </div>
                <h2 className="m-0 text-xl">从一个具体问题开始</h2>
                <p className="mt-2 mb-0 text-sm leading-relaxed text-text-muted">
                  告诉我场景、预算和偏好，或直接比较两款笔记本。
                </p>
              </div>
            ) : (
              messages.map((message) =>
                message.role === "assistant" ? (
                  <AssistantMessage
                    key={message.id}
                    message={message}
                    onFillPrompt={fillDraft}
                    onSelectSku={selectSku}
                  />
                ) : (
                  <MessageBubble key={message.id} message={message} />
                ),
              )
            )}
            {busy && (
              <div className="flex max-w-[88%] items-start gap-2.5" role="status">
                <div
                  className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border border-brand bg-brand text-xs font-extrabold text-white"
                  aria-hidden="true"
                >
                  R
                </div>
                <div className="flex gap-1 rounded-tl-none rounded-tr-2xl rounded-br-2xl rounded-bl-2xl border border-border bg-surface-soft p-4">
                  <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-brand opacity-45" />
                  <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-brand opacity-45 [animation-delay:0.15s]" />
                  <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-brand opacity-45 [animation-delay:0.3s]" />
                </div>
              </div>
            )}
          </div>
          {error && (
            <div className={cn(ERROR_STATE, "mx-5.5 mb-4")} role="alert">
              <div>
                <strong className="text-[0.78rem]">这次没有完成</strong>
                <p className="mt-0.5 text-[0.78rem] leading-tight">{error}</p>
              </div>
              <button
                className={TEXT_BUTTON}
                disabled={busy}
                onClick={retryLastMessage}
                type="button"
              >
                重试
              </button>
            </div>
          )}
          <form className="border-t border-border px-5.5 pt-4 pb-3" onSubmit={handleSubmit}>
            <label className="sr-only" htmlFor="chat-message">
              输入购物问题
            </label>
            <textarea
              ref={inputRef}
              className="w-full resize-y rounded-md border border-border-strong bg-surface p-3.5 text-text-primary"
              data-testid="chat-input"
              id="chat-message"
              onChange={(event) => setDraft(event.target.value)}
              placeholder="描述你的购物需求…"
              rows={2}
              value={draft}
            />
            <div className="mt-2.5 flex flex-wrap items-center gap-3 text-xs text-text-muted">
              <div
                className="inline-flex gap-0.5 rounded-sm border border-border bg-surface-soft p-[0.16rem]"
                aria-label="回答方式"
                role="group"
              >
                <button
                  aria-pressed={transport === "stream"}
                  className={`${TOGGLE_BUTTON} ${transport === "stream" ? TOGGLE_BUTTON_SELECTED : ""}`}
                  onClick={() => setTransport("stream")}
                  type="button"
                >
                  实时过程
                </button>
                <button
                  aria-pressed={transport === "json"}
                  className={`${TOGGLE_BUTTON} ${transport === "json" ? TOGGLE_BUTTON_SELECTED : ""}`}
                  data-testid="json-mode-button"
                  onClick={() => setTransport("json")}
                  type="button"
                >
                  快速回答
                </button>
              </div>
              <span className="mr-auto">
                {transport === "stream" ? "POST SSE · 断开仅停止接收" : "POST JSON"}
              </span>
              <Button data-testid="send-button" disabled={!draft.trim() || busy} type="submit">
                {busy ? "分析中" : "发送"}
              </Button>
            </div>
          </form>
          <div className="flex flex-wrap gap-2 px-5.5 pb-4.5" aria-label="常用问题">
            {QUICK_PROMPTS.map((prompt) => (
              <button
                className="min-h-9 cursor-pointer rounded-full border border-transparent bg-surface-soft px-2.5 text-xs text-text-muted transition-colors duration-150 ease-standard hover:border-brand/25 hover:bg-brand-soft hover:text-brand-strong disabled:cursor-not-allowed"
                key={prompt}
                disabled={busy}
                onClick={() => fillDraft(prompt)}
                type="button"
              >
                {prompt}
              </button>
            ))}
          </div>
          {actionSession && (
            <ActionDrawer
              action={actionSession.action}
              busy={actionBusy}
              error={actionError}
              resolution={resolution}
              onCancel={() => submitAction(false)}
              onConfirm={(fields) => submitAction(true, fields)}
              onDismiss={dismissAction}
            />
          )}
        </div>
      </div>
    </section>
  );
}
