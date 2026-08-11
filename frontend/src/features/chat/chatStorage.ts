const THREAD_STORAGE_KEY = "shopmind.frontend.thread_id";

function newOpaqueId(prefix: string): string {
  const randomId = typeof crypto.randomUUID === "function"
    ? crypto.randomUUID()
    : Math.random().toString(36).slice(2);
  return `${prefix}-${randomId}`;
}

export function readOrCreateThreadId(): string {
  const existing = window.localStorage.getItem(THREAD_STORAGE_KEY);
  if (existing) return existing;
  const created = newOpaqueId("thread");
  window.localStorage.setItem(THREAD_STORAGE_KEY, created);
  return created;
}

export function createThreadId(): string {
  const created = newOpaqueId("thread");
  window.localStorage.setItem(THREAD_STORAGE_KEY, created);
  return created;
}
