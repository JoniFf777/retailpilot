import type { ReactNode } from "react";
import { cn } from "../cn";

export interface EmptyProps {
  title: string;
  description?: string;
  action?: ReactNode;
  className?: string;
}

export function Empty({ title, description, action, className }: EmptyProps) {
  return (
    <div
      className={cn(
        "grid justify-items-center gap-2 rounded-lg border border-dashed border-border-strong bg-surface-raised px-6 py-8 text-center",
        className,
      )}
    >
      <p className="m-0 text-base font-semibold text-text-primary">{title}</p>
      {description ? <p className="m-0 text-sm text-text-muted">{description}</p> : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}
