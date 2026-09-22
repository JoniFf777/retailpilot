import { useContext, useRef } from "react";
import { QueryClient, QueryClientContext, useQuery } from "@tanstack/react-query";
import { shopMindApi } from "../../api/client";
import { readReadiness, type ReadinessReport } from "./readiness";

/**
 * The app shell's two status lights (desktop sidebar + mobile topbar) and StatusPage's
 * own readiness card all call this hook with the same query key, so they share one
 * cached result and one network request instead of three independent pings.
 *
 * `App` renders unconditionally (it is not behind a route), so this hook must not throw
 * when no `QueryClientProvider` is mounted above it — that happens today in App.test.tsx,
 * which renders `<App />` directly without the app's providers. A real QueryClient is
 * always present at runtime (see `AppProviders`); the lazily-created fallback below only
 * exists to keep this hook safe to call in that unprovided case, and never fetches
 * (`enabled` is false whenever it would be used).
 */
export function useSystemReadiness() {
  const contextClient = useContext(QueryClientContext);
  const fallbackClientRef = useRef<QueryClient | null>(null);
  if (!contextClient && !fallbackClientRef.current) {
    fallbackClientRef.current = new QueryClient();
  }

  return useQuery(
    {
      queryKey: ["readiness"],
      queryFn: async ({ signal }): Promise<ReadinessReport> =>
        readReadiness(await shopMindApi.readiness(signal)),
      enabled: contextClient != null,
    },
    contextClient ? undefined : (fallbackClientRef.current ?? undefined),
  );
}
