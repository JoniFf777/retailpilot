import { describe, expect, it, vi } from "vitest";
import { shopMindApi } from "../../api/client";

function streamResponse() {
  const event = {
    sequence: 1,
    event_type: "run.result",
    timestamp: "2026-08-18T00:00:00Z",
    visibility: "client",
    payload: {
      answer: "ok",
      status: "completed",
      tool_calls: [],
      retry_state: "terminal",
    },
  };
  const body = `event: run.result\nid: 1\ndata: ${JSON.stringify(event)}\n\n`;
  return new Response(new TextEncoder().encode(body), {
    status: 200,
    headers: { "Content-Type": "text/event-stream" },
  });
}

describe("Chat logical retry identity", () => {
  it("reuses the caller-owned key for repeated SSE transport attempts", async () => {
    const fetchMock = vi.fn().mockResolvedValue(streamResponse());
    vi.stubGlobal("fetch", fetchMock);
    const request = { message: "recommend a keyboard", thread_id: "thread-1", include_debug: false };
    const consume = async () => {
      for await (const event of shopMindApi.streamChat(request, "chat-idem-1")) {
        expect(event.event_type).toBe("run.result");
      }
    };
    await consume();
    await consume();
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(new Headers(fetchMock.mock.calls[0]?.[1]?.headers).get("Idempotency-Key")).toBe("chat-idem-1");
    expect(new Headers(fetchMock.mock.calls[1]?.[1]?.headers).get("Idempotency-Key")).toBe("chat-idem-1");
  });
});
