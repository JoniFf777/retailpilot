/**
 * Shared readiness response shape and parser. Used by `useSystemReadiness` (the app
 * shell's status lights) and `StatusPage` (the full readiness report), so both read
 * the same fields the same way.
 */
export interface ReadinessCheck {
  check_id: string;
  status: string;
  reason: string;
}

export interface ReadinessReport {
  profile: string;
  status: string;
  passed_checks: number;
  total_checks: number;
  failed_checks: number;
  checks: ReadinessCheck[];
}

export function readReadiness(value: unknown): ReadinessReport {
  const report = value && typeof value === "object" ? (value as Record<string, unknown>) : {};
  const checks = Array.isArray(report.checks)
    ? report.checks.flatMap((check) =>
        check &&
        typeof check === "object" &&
        typeof (check as Record<string, unknown>).check_id === "string" &&
        typeof (check as Record<string, unknown>).status === "string" &&
        typeof (check as Record<string, unknown>).reason === "string"
          ? [
              {
                check_id: String((check as Record<string, unknown>).check_id),
                status: String((check as Record<string, unknown>).status),
                reason: String((check as Record<string, unknown>).reason),
              },
            ]
          : [],
      )
    : [];
  return {
    profile: typeof report.profile === "string" ? report.profile : "unknown",
    status: typeof report.status === "string" ? report.status : "unknown",
    passed_checks: typeof report.passed_checks === "number" ? report.passed_checks : 0,
    total_checks: typeof report.total_checks === "number" ? report.total_checks : 0,
    failed_checks: typeof report.failed_checks === "number" ? report.failed_checks : 0,
    checks,
  };
}
