import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError } from "../../api/errors";
import { shopMindApi } from "../../api/client";
import type {
  ActionErrorResponse,
  ChatRequest,
  ChatResponse,
  PendingActionTransitionRequest,
  PendingActionView,
  RecommendationContextView,
} from "../../api/contracts";
import { useSession } from "../../app/useSession";
import { cartQueryKey } from "../cart/cartQuery";
import { clearCheckoutAttempt } from "../checkout/checkoutAttempt";
import { checkoutPreviewQueryKey } from "../checkout/checkoutQuery";
import { chatErrorMessage } from "./chatErrors";
import { createThreadId, readOrCreateThreadId } from "./chatStorage";
import type { ChatMessage } from "./chatTypes";
import { initialStreamState, streamReducer, type StreamState } from "./streamReducer";

type ActionMode = "structured_catalog" | "legacy_chat";
type ActionSession = {
  mode: ActionMode;
  action: PendingActionView;
  sourceRunId?: string;
  serverBacked: boolean;
};
type RetryIdentityScope = { threadId: string; ownerScope: string };
type LogicalUserMessage = ChatMessage & {
  role: "user";
  idempotencyKey: string;
  retryState: "pending" | "interrupted" | "terminal";
  retryScope: RetryIdentityScope;
};
type ActionResolution = {
  requested_quantity?: number | null;
  cart_quantity?: number | null;
  price_changed?: boolean;
  idempotent_replay?: boolean;
};

function newId(prefix: string): string {
  const value =
    typeof crypto.randomUUID === "function"
      ? crypto.randomUUID()
      : Math.random().toString(36).slice(2);
  return `${prefix}-${value}`;
}

function compatibilityAction(response: ChatResponse): PendingActionView | null {
  if (!response.pending_action_id) return null;
  const savePreference = response.tool_calls?.includes("prepare_save_preference");
  return {
    pending_action_id: response.pending_action_id,
    action_type: savePreference ? "save_preference" : "add_to_cart",
    risk_class: savePreference ? "medium" : "high",
    status: "pending",
    version: 1,
    expires_at: null,
    preview: response.answer,
    editable_fields: savePreference
      ? [
          {
            field_type: "enum",
            field: "preference_type",
            label: "Preference type",
            current_value: "other",
            options: ["budget", "brand", "avoid", "usage", "style", "other"],
            required: true,
          },
          {
            field_type: "text",
            field: "preference_value",
            label: "Preference value",
            current_value: "",
            min_length: 1,
            max_length: 2000,
            required: true,
          },
        ]
      : [
          {
            field_type: "integer",
            field: "quantity",
            label: "Quantity",
            current_value: 1,
            min_value: 1,
            max_value: 20,
            required: true,
          },
        ],
    confirm_label: "Confirm",
    cancel_label: "Cancel",
  };
}

/** Owns every piece of ChatPage's session state (thread identity, message log, in-flight
 *  stream, pending action, cart-enablement) so ChatPage.tsx itself only renders. Splitting
 *  this out doesn't change any request shape, retry semantics, or DOM output — it's a pure
 *  state-management extraction, verified by the existing ChatPage/ChatCheckoutInvalidation/
 *  ChatRetryIdempotency test suites staying green with zero test-file changes. */
export function useChatSession() {
  const [threadId, setThreadId] = useState(readOrCreateThreadId);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [lastRetryMessage, setLastRetryMessage] = useState<LogicalUserMessage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [transport, setTransport] = useState<"json" | "stream">("stream");
  const [streamState, setStreamState] = useState<StreamState>(initialStreamState);
  const streamStateRef = useRef(initialStreamState);
  const abortRef = useRef<AbortController | null>(null);
  const activeMessageRef = useRef<LogicalUserMessage | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const [actionSession, setActionSession] = useState<ActionSession | null>(null);
  const [actionError, setActionError] = useState<ActionErrorResponse | null>(null);
  const [resolution, setResolution] = useState<ActionResolution | null>(null);
  const [cartEnabled, setCartEnabled] = useState(false);
  const { isDevelopment, userId, setUserId } = useSession();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const threadShortId = useMemo(() => threadId.slice(-12), [threadId]);
  const streamBusy = streamState.status === "connecting" || streamState.status === "running";

  function currentRetryScope(): RetryIdentityScope {
    return { threadId, ownerScope: isDevelopment ? userId.trim() : "trusted" };
  }
  function requestFor(message: LogicalUserMessage): ChatRequest {
    return {
      message: message.content,
      include_debug: false,
      thread_id: message.retryScope.threadId,
      ...(isDevelopment && message.retryScope.ownerScope
        ? { user_id: message.retryScope.ownerScope }
        : {}),
    };
  }
  function appendAssistant(response: ChatResponse) {
    setMessages((current) => [
      ...current,
      { id: newId("message"), role: "assistant", content: response.answer, response },
    ]);
  }
  function updateStream(action: Parameters<typeof streamReducer>[1]): StreamState {
    const next = streamReducer(streamStateRef.current, action);
    streamStateRef.current = next;
    setStreamState(next);
    return next;
  }

  async function loadLegacyAction(response: ChatResponse) {
    if (!response.pending_action_id) return;
    try {
      const action = await shopMindApi.getPendingAction(
        response.pending_action_id,
        threadId,
        isDevelopment && userId.trim() ? userId.trim() : undefined,
      );
      setActionSession({ mode: "legacy_chat", action, serverBacked: true });
      setActionError(null);
      setResolution(null);
    } catch (requestError) {
      setActionError(
        requestError instanceof ApiError && requestError.actionError
          ? requestError.actionError
          : null,
      );
      const fallback = compatibilityAction(response);
      if (fallback?.action_type === "save_preference")
        setActionSession({ mode: "legacy_chat", action: fallback, serverBacked: false });
      else setActionSession(null);
    }
  }

  function updateLogicalMessage(
    message: LogicalUserMessage,
    retryState: LogicalUserMessage["retryState"],
  ) {
    setMessages((current) =>
      current.map((item) => (item.id === message.id ? { ...item, retryState } : item)),
    );
  }

  async function handleAssistantResponse(response: ChatResponse, message: LogicalUserMessage) {
    if (response.retry_state === "in_progress") {
      const recoverable = { ...message, retryState: "interrupted" as const };
      updateLogicalMessage(message, "interrupted");
      setLastRetryMessage(recoverable);
      setError("本次请求仍在处理中，可以稍后重试获取结果。 ");
      return;
    }
    updateLogicalMessage(message, "terminal");
    setLastRetryMessage(
      response.status === "failed" || response.status === "cancelled"
        ? { ...message, retryState: "terminal" }
        : null,
    );
    appendAssistant(response);
    if (response.status === "confirmation_required" && response.pending_action_id)
      await loadLegacyAction(response);
  }

  const chatMutation = useMutation({
    mutationFn: (message: LogicalUserMessage) =>
      shopMindApi.chat(requestFor(message), message.idempotencyKey),
    onSuccess: (response, message) => {
      void handleAssistantResponse(response, message);
      if (response.retry_state === "in_progress")
        setError("本次请求仍在处理中，可以稍后重试获取结果。 ");
      else setError(response.status === "failed" ? response.answer : null);
    },
    onError: (requestError, message) => {
      const interrupted = { ...message, retryState: "interrupted" as const };
      updateLogicalMessage(message, "interrupted");
      setLastRetryMessage(interrupted);
      setError(chatErrorMessage(requestError));
    },
  });

  const actionMutation = useMutation({
    mutationFn: async ({
      confirmed,
      updatedFields,
    }: {
      confirmed: boolean;
      updatedFields?: PendingActionTransitionRequest["updated_fields"];
    }) => {
      if (!actionSession) throw new Error("No pending action");
      if (actionSession.mode === "structured_catalog") {
        const request = {
          thread_id: threadId,
          expected_version: actionSession.action.version,
          ...(isDevelopment && userId.trim() ? { user_id: userId.trim() } : {}),
          ...(confirmed ? { updated_fields: updatedFields ?? undefined } : {}),
        };
        return confirmed
          ? shopMindApi.confirmPendingAction(actionSession.action.pending_action_id, request)
          : shopMindApi.cancelPendingAction(actionSession.action.pending_action_id, {
              thread_id: threadId,
              expected_version: actionSession.action.version,
              ...(isDevelopment && userId.trim() ? { user_id: userId.trim() } : {}),
            });
      }
      if (actionSession.action.action_type === "add_to_cart" && !actionSession.serverBacked)
        throw new Error("请重新加载待确认动作后再确认加购。");
      return shopMindApi.confirm({
        user_id: userId.trim(),
        pending_action_id: actionSession.action.pending_action_id,
        confirmed,
        thread_id: threadId,
        include_debug: false,
        ...(actionSession.action.action_type === "add_to_cart"
          ? { expected_version: actionSession.action.version }
          : {}),
        ...(updatedFields ? { updated_arguments: updatedFields } : {}),
      });
    },
    onSuccess: async (result, variables) => {
      const canonicalCartAdd =
        variables.confirmed &&
        actionSession?.action.action_type === "add_to_cart" &&
        (("pending_action" in result && result.pending_action.status === "confirmed") ||
          (!("pending_action" in result) && result.status === "completed"));
      const identity = isDevelopment ? userId.trim() : "trusted";
      if (canonicalCartAdd) {
        clearCheckoutAttempt(identity);
        queryClient.removeQueries({ queryKey: checkoutPreviewQueryKey(identity) });
        setCartEnabled(true);
        void queryClient.invalidateQueries({ queryKey: cartQueryKey(identity) });
      }
      if ("pending_action" in result) {
        setActionSession((current) =>
          current ? { ...current, action: result.pending_action } : current,
        );
        setResolution(result);
        setActionError(null);
        setCartEnabled(true);
      } else {
        appendAssistant(result);
        if (result.pending_action_id) await loadLegacyAction(result);
        else setActionSession(null);
      }
    },
    onError: async (requestError) => {
      const action = requestError instanceof ApiError ? requestError.actionError : null;
      setActionError(action);
      if (
        action &&
        [
          "action_expired",
          "product_inactive",
          "sku_inactive",
          "catalog_not_found",
          "catalog_identity_changed",
          "action_resolution_conflict",
        ].includes(action.code) &&
        actionSession
      ) {
        try {
          const refreshed = await shopMindApi.getPendingAction(
            actionSession.action.pending_action_id,
            threadId,
            isDevelopment && userId.trim() ? userId.trim() : undefined,
          );
          setActionSession((current) => (current ? { ...current, action: refreshed } : current));
        } catch {
          /* retain typed error */
        }
      }
    },
  });

  async function runStream(message: LogicalUserMessage) {
    const controller = new AbortController();
    abortRef.current = controller;
    activeMessageRef.current = message;
    updateStream({ type: "start" });
    let responseAdded = false;
    try {
      for await (const event of shopMindApi.streamChat(
        requestFor(message),
        message.idempotencyKey,
        controller.signal,
      )) {
        const next = updateStream({ type: "event", event });
        if (next.response && !responseAdded) {
          responseAdded = true;
          await handleAssistantResponse(next.response, message);
        }
      }
      const finalState = updateStream({ type: "eof" });
      if (finalState.status === "in_progress") {
        setLastRetryMessage({ ...message, retryState: "interrupted" });
        setError("本次请求仍在处理中，可以稍后重试获取结果。 ");
      } else if (finalState.status === "failed" && !responseAdded) {
        updateLogicalMessage(message, "terminal");
        setLastRetryMessage({ ...message, retryState: "terminal" });
        setError(finalState.error);
      } else if (finalState.status !== "detached") setError(null);
    } catch (streamError) {
      if (controller.signal.aborted) {
        updateStream({ type: "detach" });
        const interrupted = { ...message, retryState: "interrupted" as const };
        updateLogicalMessage(message, "interrupted");
        setLastRetryMessage(interrupted);
        setError("已停止接收实时过程，可以重试获取本次结果。 ");
      } else {
        const next = updateStream({ type: "error", message: chatErrorMessage(streamError) });
        const interrupted = { ...message, retryState: "interrupted" as const };
        updateLogicalMessage(message, "interrupted");
        setLastRetryMessage(interrupted);
        setError(next.error);
      }
    } finally {
      abortRef.current = null;
      activeMessageRef.current = null;
    }
  }

  async function selectSku(skuId: string, context: RecommendationContextView) {
    if (actionSession || !context.source_run_id) return;
    try {
      const action = await shopMindApi.createAddToCartPendingAction({
        thread_id: threadId,
        source_run_id: context.source_run_id,
        sku_id: skuId,
        quantity: 1,
        ...(isDevelopment && userId.trim() ? { user_id: userId.trim() } : {}),
      });
      setActionSession({
        mode: "structured_catalog",
        action,
        sourceRunId: context.source_run_id,
        serverBacked: true,
      });
      setActionError(null);
      setResolution(null);
    } catch (requestError) {
      setActionError(requestError instanceof ApiError ? requestError.actionError : null);
    }
  }

  function submitMessage(content: string) {
    const trimmed = content.trim();
    if (!trimmed || chatMutation.isPending || actionMutation.isPending || streamBusy) return;
    const message: LogicalUserMessage = {
      id: newId("message"),
      role: "user",
      content: trimmed,
      idempotencyKey: newId("chat-idem"),
      retryState: "pending",
      retryScope: currentRetryScope(),
    };
    setMessages((current) => [...current, message]);
    setDraft("");
    setError(null);
    setLastRetryMessage(null);
    if (transport === "json") chatMutation.mutate(message);
    else void runStream(message);
  }
  function retryLastMessage() {
    if (!lastRetryMessage || chatMutation.isPending || actionMutation.isPending || streamBusy)
      return;
    const scope = currentRetryScope();
    const sameScope =
      lastRetryMessage.retryScope.threadId === scope.threadId &&
      lastRetryMessage.retryScope.ownerScope === scope.ownerScope;
    const reuseKey = sameScope && lastRetryMessage.retryState === "interrupted";
    const message: LogicalUserMessage = reuseKey
      ? { ...lastRetryMessage, retryState: "pending" }
      : {
          ...lastRetryMessage,
          id: newId("message"),
          idempotencyKey: newId("chat-idem"),
          retryState: "pending",
          retryScope: scope,
        };
    if (message.id !== lastRetryMessage.id) setMessages((current) => [...current, message]);
    else updateLogicalMessage(message, "pending");
    setLastRetryMessage(message);
    setError(null);
    if (transport === "json") chatMutation.mutate(message);
    else void runStream(message);
  }
  function submitAction(
    confirmed: boolean,
    updatedFields?: PendingActionTransitionRequest["updated_fields"],
  ) {
    if (!actionSession || actionMutation.isPending || streamBusy) return;
    actionMutation.mutate({ confirmed, updatedFields });
  }
  function startNewThread() {
    if (chatMutation.isPending || actionMutation.isPending || streamBusy) return;
    setThreadId(createThreadId());
    setMessages([]);
    setError(null);
    setLastRetryMessage(null);
    setActionSession(null);
    setActionError(null);
    setResolution(null);
    setCartEnabled(false);
    streamStateRef.current = initialStreamState;
    setStreamState(initialStreamState);
    setDraft("");
  }
  function cancelStream() {
    abortRef.current?.abort();
  }
  function fillDraft(prompt: string) {
    setDraft(prompt);
    window.requestAnimationFrame(() => inputRef.current?.focus());
  }
  const busy = chatMutation.isPending || actionMutation.isPending || streamBusy;
  const actionBusy = actionMutation.isPending || streamBusy;

  return {
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
    dismissAction: () => setActionSession(null),
  };
}
