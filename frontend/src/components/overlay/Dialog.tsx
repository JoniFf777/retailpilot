import type { HTMLAttributes, ReactNode } from "react";
import { createPortal } from "react-dom";
import { cn } from "../cn";
import { useOverlayFocusTrap } from "./useOverlayFocusTrap";

export interface DialogProps extends Omit<HTMLAttributes<HTMLDivElement>, "role"> {
  /** id of the element that labels the dialog, wired to aria-labelledby. */
  labelledBy: string;
  /** Escape and backdrop clicks call this, when given. */
  onClose?: () => void;
  children: ReactNode;
}

/**
 * A centered modal: backdrop, focus trap, Escape-to-close, `role="dialog"` +
 * `aria-modal`, rendered through a portal to `document.body`. Shares its overlay
 * behavior with `Drawer` (see `useOverlayFocusTrap`); the difference is purely
 * positioning — centered card vs. bottom-sheet/side panel.
 */
export function Dialog({ labelledBy, onClose, className, children, ...rest }: DialogProps) {
  const panelRef = useOverlayFocusTrap<HTMLDivElement>(onClose);

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        aria-hidden="true"
        className="fixed inset-0"
        onClick={onClose}
        style={{ background: "rgba(18, 36, 31, 0.45)" }}
      />
      <div
        {...rest}
        ref={panelRef}
        aria-labelledby={labelledBy}
        aria-modal="true"
        className={cn(
          "relative max-h-[85vh] w-full max-w-md overflow-y-auto rounded-xl border border-solid border-border",
          "bg-surface shadow-overlay",
          className,
        )}
        role="dialog"
        tabIndex={-1}
      >
        {children}
      </div>
    </div>,
    document.body,
  );
}
