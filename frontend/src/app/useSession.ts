import { useContext } from "react";
import { SessionContext } from "./sessionContext";
import type { SessionValue } from "./sessionContext";

export function useSession(): SessionValue {
  const value = useContext(SessionContext);
  if (!value) throw new Error("useSession must be used inside SessionProvider.");
  return value;
}
