import type { OwnerRunInspection } from "../../api/contracts";

/** One canned run, returned for any run/trace selector the demo user types — there is no
 *  real registry to look up in a static demo, and the point of this fixture is to show
 *  RunsPage's payload-free timeline actually rendering, not to validate specific IDs. */
export function demoRunInspection(runId: string, traceId: string): OwnerRunInspection {
  const startedAt = new Date(Date.now() - 45_000).toISOString();
  return {
    schema_version: "shopmind.owner-run-inspection.v1",
    run_id: runId,
    trace_id: traceId,
    thread_id: "00000000-0000-4000-7000-000000000001",
    operation: "chat",
    mode: "multi",
    status: "completed",
    started_at: startedAt,
    completed_at: new Date().toISOString(),
    pending_action_id: null,
    event_limit: 50,
    client_event_count: 4,
    events_truncated: false,
    usage: {
      step_count: 4,
      tool_call_count: 1,
      input_tokens: null,
      output_tokens: null,
      cost_usd: null,
    },
    events: [
      {
        sequence: 1,
        event_type: "run.started",
        agent_name: null,
        created_at: startedAt,
        visibility: "client",
      },
      {
        sequence: 2,
        event_type: "product_agent.completed",
        agent_name: "product_agent",
        created_at: startedAt,
        visibility: "client",
      },
      {
        sequence: 3,
        event_type: "rag_agent.completed",
        agent_name: "rag_agent",
        created_at: startedAt,
        visibility: "client",
      },
      {
        sequence: 4,
        event_type: "run.result",
        agent_name: null,
        created_at: new Date().toISOString(),
        visibility: "client",
      },
    ],
  };
}
