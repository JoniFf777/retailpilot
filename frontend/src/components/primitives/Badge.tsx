import type { HTMLAttributes } from "react";
import { cn } from "../cn";

export type BadgeTone =
  | "neutral"
  | "brand"
  | "success"
  | "warning"
  | "danger"
  | "agent-product"
  | "agent-rag"
  | "agent-preference";

const TONES: Record<BadgeTone, string> = {
  neutral: "border-border bg-surface-soft text-text-muted",
  brand: "border-brand/25 bg-brand-soft text-brand-strong",
  success: "border-success/25 bg-brand-soft text-success",
  warning: "border-warning/25 bg-warning-soft text-warning",
  danger: "border-danger/25 bg-danger-soft text-danger",
  "agent-product": "border-agent-product/30 bg-agent-product/10 text-agent-product",
  "agent-rag": "border-agent-rag/30 bg-agent-rag/10 text-agent-rag",
  "agent-preference": "border-agent-preference/30 bg-agent-preference/10 text-agent-preference",
};

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: BadgeTone;
}

export function Badge({ tone = "neutral", className, ...rest }: BadgeProps) {
  return (
    <span
      {...rest}
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-semibold",
        TONES[tone],
        className,
      )}
    />
  );
}
