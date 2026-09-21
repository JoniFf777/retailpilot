import { cn } from "../cn";

interface SpinnerProps {
  /** Accessible name announced to assistive technology. */
  label?: string;
  className?: string;
}

export function Spinner({ label = "加载中", className }: SpinnerProps) {
  return (
    <svg
      aria-label={label}
      className={cn("size-4 animate-spin text-current motion-reduce:animate-none", className)}
      fill="none"
      role="img"
      viewBox="0 0 24 24"
    >
      <circle className="opacity-25" cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="3" />
      <path
        className="opacity-90"
        d="M21 12a9 9 0 0 0-9-9"
        stroke="currentColor"
        strokeLinecap="round"
        strokeWidth="3"
      />
    </svg>
  );
}
