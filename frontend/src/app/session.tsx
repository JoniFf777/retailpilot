import { useCallback, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { SessionContext } from "./sessionContext";
import { clearAllCheckoutAttempts } from "../features/checkout/checkoutAttempt";

export function SessionProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [userId, setUserIdState] = useState("demo-user");
  const isDevelopment = import.meta.env.DEV || import.meta.env.VITE_SHOPMIND_DEMO_IDENTITY === "true";
  const setUserId = useCallback((nextUserId: string) => {
    setUserIdState(nextUserId);
    clearAllCheckoutAttempts();
    queryClient.clear();
  }, [queryClient]);
  const value = useMemo(() => ({ isDevelopment, userId, setUserId }), [isDevelopment, userId, setUserId]);
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}
