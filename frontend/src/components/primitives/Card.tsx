import type { HTMLAttributes } from "react";
import { cn } from "../cn";

export interface CardProps extends HTMLAttributes<HTMLElement> {
  /** Element to render. Use `article` when the card is a self-contained item. */
  as?: "div" | "section" | "article";
  padded?: boolean;
}

export function Card({ as: Element = "div", padded = true, className, ...rest }: CardProps) {
  return (
    <Element
      {...rest}
      className={cn(
        "rounded-lg border border-solid border-border bg-surface shadow-soft",
        padded && "p-5",
        className,
      )}
    />
  );
}
