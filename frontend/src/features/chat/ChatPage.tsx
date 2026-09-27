import type { FormEvent } from "react";
import { Link } from "react-router-dom";
import { ActionDrawer } from "../actions/ActionDrawer";
import { CartPanel } from "../cart/CartPanel";
import { AssistantMessage } from "./AssistantMessage";
import { ExecutionTimeline } from "./ExecutionTimeline";
import { MessageBubble } from "./MessageBubble";
import { useChatSession } from "./useChatSession";

const QUICK_PROMPTS = [
  "预算 6000 元以内，主要用于 Java 开发，内存至少 16GB，希望尽量轻",
  "预算 12000 元以内，想买适合开发和出差的轻薄笔记本",
  "TECH-LAP-001 多少钱？",
];

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
    <section className="chat-page" aria-labelledby="chat-title">
      <div className="chat-heading">
        <div>
          <p className="eyebrow">RETAILPILOT WORKBENCH</p>
          <h1 id="chat-title">把购物问题，变成清晰决定</h1>
          <p className="chat-subtitle">
            用中文描述需求，RetailPilot 会整理商品信息、偏好与决策依据。
          </p>
        </div>
        <div className="chat-heading-actions">
          <Link className="secondary-button" to="/tasks">
            进入持久任务
          </Link>
          <button
            className="secondary-button"
            disabled={busy}
            onClick={startNewThread}
            type="button"
          >
            新建会话
          </button>
        </div>
      </div>
      <div className="chat-layout">
        <aside className="context-panel" aria-label="会话信息">
          <div className="panel-heading">
            <span>当前会话</span>
            <span className="online-dot">在线</span>
          </div>
          <div className="thread-card">
            <span className="label">Thread</span>
            <code>{threadShortId}</code>
            <small>Action 只绑定当前 thread 和消息的 recommendation_context。</small>
          </div>
          {isDevelopment && (
            <label className="field-label" htmlFor="dev-user-id">
              开发用户标识
              <input
                id="dev-user-id"
                value={userId}
                onChange={(event) => setUserId(event.target.value)}
              />
            </label>
          )}
          <div className="boundary-card">
            <span className="label">安全边界</span>
            <p>商品选择进入结构化 PendingAction；确认和取消分别通过专用端点。</p>
          </div>
          <CartPanel enabled={cartEnabled} onCheckout={() => navigate("/checkout")} />
        </aside>
        <div className="conversation-card">
          <div className="conversation-header">
            <div>
              <strong>购物决策对话</strong>
              <span>{transport === "stream" ? "Ordered POST-SSE" : "POST JSON"}</span>
            </div>
            <div className="conversation-actions">
              {busy && (
                <span className="pending-label" role="status">
                  处理中…
                </span>
              )}
              {streamBusy && (
                <button className="text-button" onClick={cancelStream} type="button">
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
          <div aria-live="polite" className="messages" data-testid="message-list">
            {messages.length === 0 ? (
              <div className="empty-conversation">
                <div className="empty-icon" aria-hidden="true">
                  ⌁
                </div>
                <h2>从一个具体问题开始</h2>
                <p>告诉我场景、预算和偏好，或直接比较两款笔记本。</p>
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
              <div className="message-row message-row-assistant" role="status">
                <div className="message-avatar" aria-hidden="true">
                  R
                </div>
                <div className="message-bubble typing-bubble">
                  <span />
                  <span />
                  <span />
                </div>
              </div>
            )}
          </div>
          {error && (
            <div className="error-state" role="alert">
              <div>
                <strong>这次没有完成</strong>
                <p>{error}</p>
              </div>
              <button
                className="text-button"
                disabled={busy}
                onClick={retryLastMessage}
                type="button"
              >
                重试
              </button>
            </div>
          )}
          <form className="composer" onSubmit={handleSubmit}>
            <label className="sr-only" htmlFor="chat-message">
              输入购物问题
            </label>
            <textarea
              ref={inputRef}
              data-testid="chat-input"
              id="chat-message"
              onChange={(event) => setDraft(event.target.value)}
              placeholder="描述你的购物需求…"
              rows={2}
              value={draft}
            />
            <div className="composer-footer">
              <div className="transport-toggle" aria-label="回答方式" role="group">
                <button
                  aria-pressed={transport === "stream"}
                  className={transport === "stream" ? "selected" : ""}
                  onClick={() => setTransport("stream")}
                  type="button"
                >
                  实时过程
                </button>
                <button
                  aria-pressed={transport === "json"}
                  className={transport === "json" ? "selected" : ""}
                  data-testid="json-mode-button"
                  onClick={() => setTransport("json")}
                  type="button"
                >
                  快速回答
                </button>
              </div>
              <span className="composer-hint">
                {transport === "stream" ? "POST SSE · 断开仅停止接收" : "POST JSON"}
              </span>
              <button
                className="primary-button"
                data-testid="send-button"
                disabled={!draft.trim() || busy}
                type="submit"
              >
                {busy ? "分析中" : "发送"}
              </button>
            </div>
          </form>
          <div className="quick-prompts" aria-label="常用问题">
            {QUICK_PROMPTS.map((prompt) => (
              <button key={prompt} disabled={busy} onClick={() => fillDraft(prompt)} type="button">
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
