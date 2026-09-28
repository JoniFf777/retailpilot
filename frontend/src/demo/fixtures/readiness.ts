import type { ReadinessReport } from "../../features/status/readiness";

/** A fully-passing readiness report, so the app shell's status lights and StatusPage both
 *  show "ready" under demo mode instead of the "unknown" state a 501 produces — a demo
 *  visitor shouldn't see a warning light on a page that has nothing wrong with it. */
export function demoReadinessReport(): ReadinessReport {
  const checks = [
    { check_id: "database.connectivity", status: "passed", reason: "ok" },
    { check_id: "rocketmq.connectivity", status: "passed", reason: "ok" },
    { check_id: "model_gateway.reachable", status: "passed", reason: "ok" },
  ];
  return {
    profile: "demo",
    status: "ready",
    passed_checks: checks.length,
    total_checks: checks.length,
    failed_checks: 0,
    checks,
  };
}
