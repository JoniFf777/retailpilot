import type { ReactNode } from "react";
import { cn } from "../cn";

export interface FieldProps {
  /** Must match the `id` of the control passed as children. */
  htmlFor: string;
  label: string;
  hint?: string;
  error?: string | null;
  className?: string;
  children: ReactNode;
}

/** Label + control + hint/error. The caller owns the control and its `id`. */
export function Field({ htmlFor, label, hint, error, className, children }: FieldProps) {
  return (
    <div className={cn("grid gap-1.5", className)}>
      <label className="text-sm font-semibold text-text-primary" htmlFor={htmlFor}>
        {label}
      </label>
      {children}
      {hint && !error ? <p className="m-0 text-xs text-text-muted">{hint}</p> : null}
      {error ? (
        <p className="m-0 text-xs text-danger" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
