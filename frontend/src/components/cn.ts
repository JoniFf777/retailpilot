export type ClassValue = string | false | null | undefined;

/** Joins class names, skipping falsy values. Deliberately tiny: no conflict resolution. */
export function cn(...parts: ClassValue[]): string {
  return parts.filter(Boolean).join(" ");
}
