export function createId(prefix: string): string {
  const value = typeof crypto.randomUUID === "function" ? crypto.randomUUID() : Math.random().toString(36).slice(2);
  return `${prefix}-${value}`;
}
