import { useEffect, useRef } from "react";

interface CartConfirmationDialogProps {
  title: string;
  description: string;
  confirmLabel: string;
  busy?: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}

export function CartConfirmationDialog({ title, description, confirmLabel, busy = false, onCancel, onConfirm }: CartConfirmationDialogProps) {
  const cancelRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    cancelRef.current?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) onCancel();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [busy, onCancel]);

  return <div className="cart-dialog-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) onCancel(); }}>
    <div className="cart-confirmation-dialog" role="dialog" aria-modal="true" aria-labelledby="cart-confirmation-title" aria-describedby="cart-confirmation-description">
      <h2 id="cart-confirmation-title">{title}</h2>
      <p id="cart-confirmation-description">{description}</p>
      <div className="cart-dialog-actions">
        <button className="secondary-button" ref={cancelRef} disabled={busy} onClick={onCancel} type="button">取消</button>
        <button className="danger-button" disabled={busy} onClick={onConfirm} type="button">{busy ? "处理中…" : confirmLabel}</button>
      </div>
    </div>
  </div>;
}
