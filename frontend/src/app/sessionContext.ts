import { createContext } from "react";

export interface SessionValue {
  isDevelopment: boolean;
  userId: string;
  setUserId: (userId: string) => void;
}

export const SessionContext = createContext<SessionValue | null>(null);
