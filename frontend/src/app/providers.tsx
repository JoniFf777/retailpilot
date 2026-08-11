import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { SessionProvider } from "./session";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, retry: 1 },
    mutations: { retry: false },
  },
});

export function AppProviders({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={queryClient}><SessionProvider>{children}</SessionProvider></QueryClientProvider>;
}
