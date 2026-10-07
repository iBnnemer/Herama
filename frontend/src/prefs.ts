/** Small interface preferences kept on this computer. */
export interface Prefs { scale: number; retentionDays: number }

export const DEFAULT_PREFS: Prefs = { scale: 100, retentionDays: 0 };

export function applyScale(scale: number) {
  const z = Math.min(150, Math.max(75, scale)) / 100;
  (document.body.style as CSSStyleDeclaration & { zoom: string }).zoom = String(z);
}

/** Drop sessions whose last activity is older than `days`; pinned ones and the newest one always stay. */
export function pruneOld<T extends { id: string; pinned?: boolean; messages: { ts: number }[] }>(list: T[], days: number, now = Date.now()): T[] {
  if (days <= 0) return list;
  const limit = now - days * 86_400_000;
  const last = (c: T) => c.messages.length ? c.messages[c.messages.length - 1].ts : now;
  const kept = list.filter((c, i) => i === 0 || c.pinned || last(c) >= limit);
  return kept.length === list.length ? list : kept;
}
