import { useLayoutEffect, useRef } from "react";

const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "textarea:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  '[tabindex]:not([tabindex="-1"])',
].join(", ");

/**
 * Traps Tab/Shift+Tab focus inside the returned ref's element, moves focus into it on
 * mount, restores the previously-focused element on unmount, and calls `onClose` (if
 * given) on Escape.
 *
 * `onClose` is read through a ref, not a dependency, so the trap is set up once per
 * mount rather than re-running whenever the caller passes a fresh inline closure (every
 * render, in practice) — re-running it would steal focus back to the panel on every
 * keystroke.
 */
export function useOverlayFocusTrap<T extends HTMLElement>(onClose?: () => void) {
  const ref = useRef<T>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useLayoutEffect(() => {
    const panel = ref.current;
    if (!panel) return;
    const previouslyFocused = document.activeElement as HTMLElement | null;

    const focusables = () => Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR));
    (focusables()[0] ?? panel).focus();

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.stopPropagation();
        onCloseRef.current?.();
        return;
      }
      if (event.key !== "Tab" || !panel) return;
      const items = focusables();
      if (items.length === 0) {
        event.preventDefault();
        panel.focus();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", onKeyDown, true);
    return () => {
      document.removeEventListener("keydown", onKeyDown, true);
      if (previouslyFocused && document.contains(previouslyFocused)) previouslyFocused.focus();
    };
    // Mount/unmount only — see the onCloseRef note above. `ref` and `onCloseRef` are
    // useRef objects, which are stable across renders and exempt from exhaustive-deps.
  }, []);

  return ref;
}
