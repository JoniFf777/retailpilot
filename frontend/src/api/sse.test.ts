import { describe, expect, it } from "vitest";
import { parseSseText, toAgentEvent } from "./sse";

describe("ShopMind SSE contract", () => {
  it("parses event, id, and JSON data fields", () => {
    const frames = parseSseText('event: run.progress\nid: 3\ndata: {"sequence":3}\n\n');
    expect(frames).toEqual([{ event: "run.progress", id: "3", data: '{"sequence":3}' }]);
  });

  it("preserves multiline data and ignores comments", () => {
    const frames = parseSseText(": heartbeat\ndata: first\ndata: second\n\n");
    expect(frames[0]?.data).toBe("first\nsecond");
  });

  it("rejects an envelope whose event and sequence disagree", () => {
    expect(() => toAgentEvent({ event: "run.failed", id: "4", data: JSON.stringify({ sequence: 3, event_type: "run.result" }) })).toThrow(/mismatch/);
  });
});
