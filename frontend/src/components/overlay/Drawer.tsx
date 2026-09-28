import type { ElementType, HTMLAttributes, ReactNode } from "react";
import { createPortal } from "react-dom";
import { cn } from "../cn";
import { useOverlayFocusTrap } from "./useOverlayFocusTrap";

export interface DrawerProps extends Omit<HTMLAttributes<HTMLElement>, "role"> {
  /** Element to render the panel as. `aside` (default) matches the drawer's semantics. */
  as?: ElementType;
  /** id of the element that labels the drawer, wired to aria-labelledby. */
  labelledBy: string;
  /** Escape and backdrop clicks call this, when given. There is no default: a drawer
   *  with no way to close itself other than the caller's own controls is valid (the
   *  caller's buttons stay reachable via the focus trap either way). */
  onClose?: () => void;
  /**
   * Whether a backdrop dims the page and blocks clicks outside the panel. Defaults to
   * true. Set to false for a drawer that is meant to stay open alongside the rest of
   * the page rather than block it — e.g. ActionDrawer, which can linger showing a
   * post-confirm resolution message while the page underneath (the cart it just
   * updated) stays interactive.
   */
  backdrop?: boolean;
  children: ReactNode;
}

/**
 * A bottom-sheet-on-mobile / right-panel-on-desktop overlay: focus trap, Escape-to-
 * close, `role="dialog"` + `aria-modal`, rendered through a portal to `document.body`
 * so it sits above the rest of the page regardless of where it is mounted in the tree.
 * The backdrop (dims + blocks the rest of the page) is opt-out — see `backdrop`.
 */
export function Drawer({
  as: Element = "aside",
  labelledBy,
  onClose,
  backdrop = true,
  className,
  children,
  ...rest
}: DrawerProps) {
  const panelRef = useOverlayFocusTrap<HTMLElement>(onClose);

  return createPortal(
    <div
      className={cn(
        "fixed inset-0 z-50 flex items-end justify-center sm:items-center sm:justify-end",
        !backdrop && "pointer-events-none",
      )}
    >
      {backdrop && (
        <div
          aria-hidden="true"
          className="fixed inset-0"
          onClick={onClose}
          style={{ background: "rgba(18, 36, 31, 0.45)" }}
        />
      )}
      <Element
        {...rest}
        ref={panelRef}
        aria-labelledby={labelledBy}
        aria-modal="true"
        className={cn(
          "relative max-h-[85vh] w-full overflow-y-auto rounded-t-xl border border-border",
          "pointer-events-auto bg-surface shadow-overlay sm:m-6 sm:max-w-md sm:rounded-xl",
          className,
        )}
        role="dialog"
        tabIndex={-1}
      >
        {children}
      </Element>
    </div>,
    document.body,
  );
}
