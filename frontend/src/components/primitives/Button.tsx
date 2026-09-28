import type { ButtonHTMLAttributes } from "react";
import { cn } from "../cn";
import { Spinner } from "./Spinner";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
export type ButtonSize = "sm" | "md";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** Shows a spinner, sets aria-busy and blocks clicks. */
  loading?: boolean;
}

const VARIANTS: Record<ButtonVariant, string> = {
  primary: "border-brand bg-brand text-white hover:bg-brand-strong hover:border-brand-strong",
  secondary: "border-border-strong bg-surface text-text-primary hover:bg-surface-soft",
  ghost: "border-transparent bg-transparent text-text-muted hover:bg-surface-soft",
  danger: "border-danger bg-danger text-white hover:opacity-90",
};

const SIZES: Record<ButtonSize, string> = {
  sm: "min-h-8 gap-1.5 px-3 text-sm",
  md: "min-h-10 gap-2 px-4 text-sm",
};

export function Button({
  variant = "primary",
  size = "md",
  loading = false,
  type = "button",
  disabled,
  className,
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      {...rest}
      aria-busy={loading || undefined}
      className={cn(
        "inline-flex cursor-pointer items-center justify-center rounded-md border font-semibold",
        "transition-colors duration-150 ease-standard motion-reduce:transition-none",
        "focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-ring/30",
        "disabled:cursor-not-allowed disabled:opacity-55",
        VARIANTS[variant],
        SIZES[size],
        className,
      )}
      disabled={disabled || loading}
      type={type}
    >
      {loading ? <Spinner label="处理中" /> : null}
      {children}
    </button>
  );
}
