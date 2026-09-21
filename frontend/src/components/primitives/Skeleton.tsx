import type { HTMLAttributes } from "react";
import { cn } from "../cn";

/** Decorative loading placeholder. Pair it with a real status message for screen readers. */
export function Skeleton({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      {...rest}
      aria-hidden="true"
      className={cn(
        "animate-pulse rounded-md bg-surface-soft motion-reduce:animate-none",
        className,
      )}
    />
  );
}
