import { useContext, useRef } from "react";
import { ThemeContext, type Theme, type ThemeValue } from "./themeContext";

/**
 * `App` renders unconditionally (it is not behind a route) and calls this hook to render
 * the theme toggle, so it must not throw when no `ThemeProvider` is mounted above it —
 * that happens today in `App.test.tsx`, which renders `<App />` directly without the
 * app's providers (same reasoning as `useSystemReadiness`'s fallback `QueryClient`). A
 * real `ThemeProvider` is always present at runtime (see `AppProviders`); this fallback
 * only exists to keep the hook safe to call in that unprovided case — it never touches
 * `<html>`'s class list or storage, it just tracks local state for that one render tree.
 */
export function useTheme(): ThemeValue {
  const context = useContext(ThemeContext);
  const fallbackThemeRef = useRef<Theme>("light");
  if (context) return context;
  return {
    theme: fallbackThemeRef.current,
    setTheme: (next) => {
      fallbackThemeRef.current = next;
    },
    toggleTheme: () => {
      fallbackThemeRef.current = fallbackThemeRef.current === "dark" ? "light" : "dark";
    },
  };
}
