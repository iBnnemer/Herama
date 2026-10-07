/** Remembered approvals: "session" lasts until the app is closed, "always" is saved on this computer. */
const KEY = "herama.approvals";
const session = new Set<string>();

function saved(): string[] {
  try {
    const v = JSON.parse(localStorage.getItem(KEY) || "[]");
    return Array.isArray(v) ? v.map(String) : [];
  } catch { return []; }
}

function write(list: string[]) {
  try { localStorage.setItem(KEY, JSON.stringify(list)); } catch { /* storage unavailable */ }
}

export const approvals = {
  has: (key: string) => session.has(key) || saved().includes(key),
  remember(key: string, scope: "session" | "always") {
    if (scope === "session") session.add(key);
    else if (!saved().includes(key)) write([...saved(), key]);
  },
  forget(key: string) {
    session.delete(key);
    write(saved().filter(k => k !== key));
  },
  /** Every remembered key (both kinds) that starts with `prefix`. */
  keys(prefix = ""): string[] {
    return [...new Set([...session, ...saved()])].filter(k => k.startsWith(prefix));
  },
  always: saved,
};

/** Text for a remembered key, as shown in settings. */
export function describeKey(key: string): string {
  if (key === "computer") return "Search files on this computer";
  if (key.startsWith("tool:")) return `Run ${key.slice(5)}`;
  if (key.startsWith("read:")) return `Read files in ${key.slice(5)}`;
  if (key.startsWith("write:")) return `Change files in ${key.slice(6)}`;
  return key;
}
