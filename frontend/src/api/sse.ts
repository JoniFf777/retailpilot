import type { AgentEvent, SseFrame } from "./sseTypes";

function decodeData(data: string): AgentEvent {
  const parsed: unknown = JSON.parse(data);
  if (!parsed || typeof parsed !== "object" || !("event_type" in parsed) || !("sequence" in parsed)) {
    throw new Error("Invalid ShopMind stream event.");
  }
  return parsed as AgentEvent;
}

/** Parse standard SSE text while preserving multiline data fields. */
export function parseSseText(text: string): SseFrame[] {
  const frames: SseFrame[] = [];
  let event: string | undefined;
  let id: string | undefined;
  let data: string[] = [];

  const flush = () => {
    if (data.length === 0 && event === undefined && id === undefined) return;
    frames.push({ event, id, data: data.join("\n") });
    event = undefined;
    id = undefined;
    data = [];
  };

  for (const line of text.replaceAll("\r\n", "\n").split("\n")) {
    if (line === "") {
      flush();
      continue;
    }
    if (line.startsWith(":")) continue;
    const separator = line.indexOf(":");
    const field = separator === -1 ? line : line.slice(0, separator);
    const value = separator === -1 ? "" : line.slice(separator + 1).replace(/^ /, "");
    if (field === "event") event = value;
    if (field === "id") id = value;
    if (field === "data") data.push(value);
  }
  flush();
  return frames;
}

export function toAgentEvent(frame: SseFrame): AgentEvent {
  const event = decodeData(frame.data);
  if (frame.event && frame.event !== event.event_type) {
    throw new Error("ShopMind stream event type mismatch.");
  }
  if (frame.id && Number(frame.id) !== event.sequence) {
    throw new Error("ShopMind stream sequence mismatch.");
  }
  return event;
}

export async function* readSseStream(body: ReadableStream<Uint8Array>): AsyncGenerator<AgentEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let pending = "";
  let lastSequence = 0;

  try {
    while (true) {
      const chunk = await reader.read();
      pending += decoder.decode(chunk.value, { stream: !chunk.done });
      const sections = pending.replaceAll("\r\n", "\n").split("\n\n");
      pending = sections.pop() ?? "";
      for (const section of sections) {
        for (const frame of parseSseText(`${section}\n`)) {
          const event = toAgentEvent(frame);
          if (event.sequence <= lastSequence) continue;
          lastSequence = event.sequence;
          yield event;
        }
      }
      if (chunk.done) break;
    }
    if (pending.trim()) {
      for (const frame of parseSseText(`${pending}\n`)) {
        const event = toAgentEvent(frame);
        if (event.sequence > lastSequence) yield event;
      }
    }
  } finally {
    reader.releaseLock();
  }
}
