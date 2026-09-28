import { useEffect, useRef } from "react";
import { BUTTON_DANGER, BUTTON_SECONDARY } from "../../components/textPatterns";

interface CartConfirmationDialogProps {
  title: string;
  description: string;
  confirmLabel: string;
  busy?: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}

export function CartConfirmationDialog({
  title,
  description,
  confirmLabel,
  busy = false,
  onCancel,
  onConfirm,
}: CartConfirmationDialogProps) {
  const cancelRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    cancelRef.current?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) onCancel();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [busy, onCancel]);

  return (
    <div
      className="fixed inset-0 z-20 flex items-center justify-center p-4"
      role="presentation"
      style={{ background: "rgba(18, 36, 31, 0.38)" }}
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !busy) onCancel();
      }}
    >
      <div
        className="w-full max-w-[25rem] rounded-md border border-solid border-border-strong bg-surface p-[1.15rem] shadow-overlay"
        role="dialog"
        aria-modal="true"
        aria-labelledby="cart-confirmation-title"
        aria-describedby="cart-confirmation-description"
      >
        <h2 className="m-0 text-base" id="cart-confirmation-title">
          {title}
        </h2>
        <p
          className="mt-2.5 mb-4 text-sm leading-relaxed text-text-muted"
          id="cart-confirmation-description"
        >
          {description}
        </p>
        <div className="flex justify-end gap-2">
          <button
            className={BUTTON_SECONDARY}
            ref={cancelRef}
            disabled={busy}
            onClick={onCancel}
            type="button"
          >
            取消
          </button>
          <button className={BUTTON_DANGER} disabled={busy} onClick={onConfirm} type="button">
            {busy ? "处理中…" : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
