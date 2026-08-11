import { useMutation, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError } from "../../api/errors";
import { shopMindApi } from "../../api/client";
import type { ActionErrorResponse, ChatRequest, ChatResponse, PendingActionTransitionRequest, PendingActionView, RecommendationContextView } from "../../api/contracts";
import { useSession } from "../../app/useSession";
import { ActionDrawer } from "../actions/ActionDrawer";
import { CartPanel } from "../cart/CartPanel";
import { cartQueryKey } from "../cart/cartQuery";
import { clearCheckoutAttempt } from "../checkout/checkoutAttempt";
import { checkoutPreviewQueryKey } from "../checkout/checkoutQuery";
import { AssistantMessage } from "./AssistantMessage";
import { MessageBubble } from "./MessageBubble";
import { chatErrorMessage } from "./chatErrors";
import { createThreadId, readOrCreateThreadId } from "./chatStorage";
import type { ChatMessage } from "./chatTypes";
import { initialStreamState, streamReducer, type StreamState } from "./streamReducer";

const QUICK_PROMPTS = ["预算 6000 元以内，主要用于 Java 开发，内存至少 16GB，希望尽量轻", "预算 12000 元以内，想买适合开发和出差的轻薄笔记本", "TECH-LAP-001 多少钱？"];
type ActionMode = "structured_catalog" | "legacy_chat";
type ActionSession = { mode: ActionMode; action: PendingActionView; sourceRunId?: string };

function newId(prefix: string): string { const value = typeof crypto.randomUUID === "function" ? crypto.randomUUID() : Math.random().toString(36).slice(2); return `${prefix}-${value}`; }

export function ChatPage() {
  const [threadId, setThreadId] = useState(readOrCreateThreadId);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [lastFailedMessage, setLastFailedMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [transport, setTransport] = useState<"json" | "stream">("stream");
  const [streamState, setStreamState] = useState<StreamState>(initialStreamState);
  const streamStateRef = useRef(initialStreamState);
  const abortRef = useRef<AbortController | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const [actionSession, setActionSession] = useState<ActionSession | null>(null);
  const [actionError, setActionError] = useState<ActionErrorResponse | null>(null);
  const [resolution, setResolution] = useState<{ requested_quantity?: number | null; cart_quantity?: number | null; price_changed?: boolean; idempotent_replay?: boolean } | null>(null);
  const [cartEnabled, setCartEnabled] = useState(false);
  const { isDevelopment, userId, setUserId } = useSession();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const threadShortId = useMemo(() => threadId.slice(-12), [threadId]);
  const streamBusy = streamState.status === "connecting" || streamState.status === "running";

  function requestFor(message: string): ChatRequest { return { message, include_debug: false, thread_id: threadId, ...(isDevelopment && userId.trim() ? { user_id: userId.trim() } : {}) }; }
  function appendAssistant(response: ChatResponse) { setMessages((current) => [...current, { id: newId("message"), role: "assistant", content: response.answer, response }]); }
  function updateStream(action: Parameters<typeof streamReducer>[1]): StreamState { const next = streamReducer(streamStateRef.current, action); streamStateRef.current = next; setStreamState(next); return next; }

  function compatibilityAction(response: ChatResponse): PendingActionView | null {
    if (!response.pending_action_id) return null;
    const savePreference = response.tool_calls?.includes("prepare_save_preference");
    return { pending_action_id: response.pending_action_id, action_type: savePreference ? "save_preference" : "add_to_cart", risk_class: savePreference ? "medium" : "high", status: "pending", version: 1, expires_at: null, preview: response.answer, editable_fields: savePreference ? [{ field_type: "enum", field: "preference_type", label: "Preference type", current_value: "other", options: ["budget", "brand", "avoid", "usage", "style", "other"], required: true }, { field_type: "text", field: "preference_value", label: "Preference value", current_value: "", min_length: 1, max_length: 2000, required: true }] : [{ field_type: "integer", field: "quantity", label: "Quantity", current_value: 1, min_value: 1, max_value: 20, required: true }], confirm_label: "Confirm", cancel_label: "Cancel" };
  }

  async function loadLegacyAction(response: ChatResponse) {
    if (!response.pending_action_id) return;
    try {
      const action = await shopMindApi.getPendingAction(response.pending_action_id, threadId, isDevelopment && userId.trim() ? userId.trim() : undefined);
      setActionSession({ mode: "legacy_chat", action }); setActionError(null); setResolution(null);
    } catch (requestError) { setActionError(requestError instanceof ApiError && requestError.actionError ? requestError.actionError : null); const fallback = compatibilityAction(response); if (fallback) setActionSession({ mode: "legacy_chat", action: fallback }); }
  }

  async function handleAssistantResponse(response: ChatResponse) {
    appendAssistant(response);
    if (response.status === "confirmation_required" && response.pending_action_id) await loadLegacyAction(response);
  }

  const chatMutation = useMutation({
    mutationFn: (message: string) => shopMindApi.chat(requestFor(message)),
    onSuccess: (response, message) => { void handleAssistantResponse(response); setLastFailedMessage(response.status === "failed" ? message : null); setError(response.status === "failed" ? response.answer : null); },
    onError: (requestError, message) => { setLastFailedMessage(message); setError(chatErrorMessage(requestError)); },
  });

  const actionMutation = useMutation({
    mutationFn: async ({ confirmed, updatedFields }: { confirmed: boolean; updatedFields?: PendingActionTransitionRequest["updated_fields"] }) => {
      if (!actionSession) throw new Error("No pending action");
      if (actionSession.mode === "structured_catalog") {
        const request = { thread_id: threadId, expected_version: actionSession.action.version, ...(isDevelopment && userId.trim() ? { user_id: userId.trim() } : {}), ...(confirmed ? { updated_fields: updatedFields ?? undefined } : {}) };
        return confirmed ? shopMindApi.confirmPendingAction(actionSession.action.pending_action_id, request) : shopMindApi.cancelPendingAction(actionSession.action.pending_action_id, { thread_id: threadId, expected_version: actionSession.action.version, ...(isDevelopment && userId.trim() ? { user_id: userId.trim() } : {}) });
      }
      return shopMindApi.confirm({ user_id: userId.trim(), pending_action_id: actionSession.action.pending_action_id, confirmed, thread_id: threadId, include_debug: false, ...(updatedFields ? { updated_arguments: updatedFields } : {}) });
    },
    onSuccess: async (result, variables) => {
      if ("pending_action" in result) {
        const structuredCartAdd = variables.confirmed && actionSession?.mode === "structured_catalog" && actionSession.action.action_type === "add_to_cart";
        setActionSession((current) => current ? { ...current, action: result.pending_action } : current);
        setResolution(result);
        setActionError(null);
        setCartEnabled(true);
        const identity = isDevelopment ? userId.trim() : "trusted";
        if (structuredCartAdd) {
          clearCheckoutAttempt(identity);
          queryClient.removeQueries({ queryKey: checkoutPreviewQueryKey(identity) });
        }
        void queryClient.invalidateQueries({ queryKey: cartQueryKey(identity) });
      }
      else { appendAssistant(result); if (result.pending_action_id) await loadLegacyAction(result); else setActionSession(null); }
    },
    onError: async (requestError) => {
      const action = requestError instanceof ApiError ? requestError.actionError : null;
      setActionError(action);
      if (action && ["action_expired", "product_inactive", "sku_inactive", "catalog_not_found", "catalog_identity_changed", "action_resolution_conflict"].includes(action.code) && actionSession) {
        try { const refreshed = await shopMindApi.getPendingAction(actionSession.action.pending_action_id, threadId, isDevelopment && userId.trim() ? userId.trim() : undefined); setActionSession((current) => current ? { ...current, action: refreshed } : current); } catch { /* retain typed error */ }
      }
    },
  });

  async function runStream(message: string) {
    const controller = new AbortController(); abortRef.current = controller; updateStream({ type: "start" }); let responseAdded = false;
    try {
      for await (const event of shopMindApi.streamChat(requestFor(message), controller.signal)) {
        const next = updateStream({ type: "event", event });
        if (next.response && !responseAdded) { responseAdded = true; await handleAssistantResponse(next.response); }
      }
      const finalState = updateStream({ type: "eof" });
      if (finalState.status === "failed") { setLastFailedMessage(message); setError(finalState.error); } else { setLastFailedMessage(null); setError(null); }
    } catch (streamError) { if (controller.signal.aborted) { updateStream({ type: "cancel" }); setError(null); } else { const next = updateStream({ type: "error", message: chatErrorMessage(streamError) }); setLastFailedMessage(message); setError(next.error); } }
    finally { abortRef.current = null; }
  }

  async function selectSku(skuId: string, context: RecommendationContextView) {
    if (actionSession || !context.source_run_id) return;
    try {
      const action = await shopMindApi.createAddToCartPendingAction({ thread_id: threadId, source_run_id: context.source_run_id, sku_id: skuId, quantity: 1, ...(isDevelopment && userId.trim() ? { user_id: userId.trim() } : {}) });
      setActionSession({ mode: "structured_catalog", action, sourceRunId: context.source_run_id }); setActionError(null); setResolution(null);
    } catch (requestError) { setActionError(requestError instanceof ApiError ? requestError.actionError : null); }
  }

  function submitMessage(event: FormEvent<HTMLFormElement>) { event.preventDefault(); const message = draft.trim(); if (!message || chatMutation.isPending || actionMutation.isPending || streamBusy) return; setMessages((current) => [...current, { id: newId("message"), role: "user", content: message }]); setDraft(""); setError(null); setLastFailedMessage(null); if (transport === "json") chatMutation.mutate(message); else void runStream(message); }
  function retryLastMessage() { if (!lastFailedMessage || chatMutation.isPending || actionMutation.isPending || streamBusy) return; setError(null); if (transport === "json") chatMutation.mutate(lastFailedMessage); else void runStream(lastFailedMessage); }
  function submitAction(confirmed: boolean, updatedFields?: PendingActionTransitionRequest["updated_fields"]) { if (!actionSession || actionMutation.isPending || streamBusy) return; actionMutation.mutate({ confirmed, updatedFields }); }
  function startNewThread() { if (chatMutation.isPending || actionMutation.isPending || streamBusy) return; setThreadId(createThreadId()); setMessages([]); setError(null); setLastFailedMessage(null); setActionSession(null); setActionError(null); setResolution(null); setCartEnabled(false); streamStateRef.current = initialStreamState; setStreamState(initialStreamState); setDraft(""); }
  function cancelStream() { abortRef.current?.abort(); }
  function fillDraft(prompt: string) { setDraft(prompt); window.requestAnimationFrame(() => inputRef.current?.focus()); }
  const busy = chatMutation.isPending || actionMutation.isPending || streamBusy;

  return <section className="chat-page" aria-labelledby="chat-title">
    <div className="chat-heading"><div><p className="eyebrow">SHOPMIND WORKBENCH</p><h1 id="chat-title">把购物问题，变成清晰决定</h1><p className="chat-subtitle">用中文描述需求，ShopMind 会整理商品信息、偏好与决策依据。</p></div><button className="secondary-button" disabled={busy} onClick={startNewThread} type="button">新建会话</button></div>
    <div className="chat-layout"><aside className="context-panel" aria-label="会话信息"><div className="panel-heading"><span>当前会话</span><span className="online-dot">在线</span></div><div className="thread-card"><span className="label">Thread</span><code>{threadShortId}</code><small>Action 只绑定当前 thread 和消息的 recommendation_context。</small></div>{isDevelopment && <label className="field-label" htmlFor="dev-user-id">开发用户标识<input id="dev-user-id" value={userId} onChange={(event) => setUserId(event.target.value)} /></label>}<div className="boundary-card"><span className="label">安全边界</span><p>商品选择进入结构化 PendingAction；确认和取消分别通过专用端点。</p></div><CartPanel enabled={cartEnabled} onCheckout={() => navigate("/checkout")} /></aside>
      <div className="conversation-card"><div className="conversation-header"><div><strong>购物决策对话</strong><span>{transport === "stream" ? "Ordered POST-SSE" : "POST JSON"}</span></div><div className="conversation-actions">{busy && <span className="pending-label" role="status">处理中…</span>}{streamBusy && <button className="text-button" onClick={cancelStream} type="button">停止</button>}</div></div>{streamState.progress.length > 0 && streamBusy && <div className="stream-progress" aria-live="polite"><div className="stream-progress-heading"><span>实时执行进度</span><span>{streamState.lastSequence} 个事件</span></div><div className="stream-progress-list">{streamState.progress.map((item) => <span key={item.sequence}>{item.agentName ? `${item.agentName} · ` : ""}{item.label}</span>)}</div></div>}<div aria-live="polite" className="messages" data-testid="message-list">{messages.length === 0 ? <div className="empty-conversation"><div className="empty-icon" aria-hidden="true">⌁</div><h2>从一个具体问题开始</h2><p>告诉我场景、预算和偏好，或直接比较两款笔记本。</p></div> : messages.map((message) => message.role === "assistant" ? <AssistantMessage key={message.id} message={message} onFillPrompt={fillDraft} onSelectSku={selectSku} /> : <MessageBubble key={message.id} message={message} />)}{busy && <div className="message-row message-row-assistant" role="status"><div className="message-avatar" aria-hidden="true">S</div><div className="message-bubble typing-bubble"><span /><span /><span /></div></div>}</div>{error && <div className="error-state" role="alert"><div><strong>这次没有完成</strong><p>{error}</p></div><button className="text-button" disabled={busy} onClick={retryLastMessage} type="button">重试</button></div>}<form className="composer" onSubmit={submitMessage}><label className="sr-only" htmlFor="chat-message">输入购物问题</label><textarea ref={inputRef} data-testid="chat-input" id="chat-message" onChange={(event) => setDraft(event.target.value)} placeholder="描述你的购物需求…" rows={2} value={draft} /><div className="composer-footer"><div className="transport-toggle" aria-label="回答方式" role="group"><button aria-pressed={transport === "stream"} className={transport === "stream" ? "selected" : ""} onClick={() => setTransport("stream")} type="button">实时过程</button><button aria-pressed={transport === "json"} className={transport === "json" ? "selected" : ""} data-testid="json-mode-button" onClick={() => setTransport("json")} type="button">快速回答</button></div><span className="composer-hint">{transport === "stream" ? "POST SSE · 可随时停止" : "POST JSON"}</span><button className="primary-button" data-testid="send-button" disabled={!draft.trim() || busy} type="submit">{busy ? "分析中" : "发送"}</button></div></form><div className="quick-prompts" aria-label="常用问题">{QUICK_PROMPTS.map((prompt) => <button key={prompt} disabled={busy} onClick={() => fillDraft(prompt)} type="button">{prompt}</button>)}</div>{actionSession && <ActionDrawer action={actionSession.action} busy={actionMutation.isPending || streamBusy} error={actionError} resolution={resolution} onCancel={() => submitAction(false)} onConfirm={(fields) => submitAction(true, fields)} onDismiss={() => setActionSession(null)} />}</div>
    </div>
  </section>;
}
