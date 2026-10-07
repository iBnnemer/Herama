import { useEffect, useState } from "react";
import type { Dispatch, SetStateAction } from "react";

export function usePersistent<T>(
  key: string,
  initial: T,
  revive: (v: T) => T = v => v,
): [T, Dispatch<SetStateAction<T>>] {
  const [value, setValue] = useState<T>(() => {
    try {
      const raw = localStorage.getItem(key);
      return raw ? revive(JSON.parse(raw) as T) : initial;
    } catch {
      return initial;
    }
  });

  useEffect(() => {
    const t = setTimeout(() => {
      try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* storage unavailable or full */ }
    }, 400);
    return () => clearTimeout(t);
  }, [key, value]);

  return [value, setValue];
}
