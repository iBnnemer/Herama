import { useEffect, useRef, useState } from "react";
import type { Effort } from "../types";
import { EFFORT_LEVELS, EFFORT_PARAMS } from "../types";
import Icon from "./Icons";

interface Props { effort: Effort; onChange: (e: Effort) => void }

export default function EffortPicker({ effort, onChange }: Props) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const last = EFFORT_LEVELS.length - 1;
  const idx = EFFORT_LEVELS.indexOf(effort);
  const at = (i: number) => `${(i / last) * 100}%`;

  useEffect(() => {
    if (!open) return;
    const h = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    window.addEventListener("mousedown", h);
    return () => window.removeEventListener("mousedown", h);
  }, [open]);

  return (
    <div ref={box} style={{ position: "relative" }}>
      <button onClick={() => setOpen(o => !o)} style={{
        display: "flex", alignItems: "center", gap: 5, padding: "4px 8px",
        background: "transparent", border: "none", borderRadius: 8,
        color: "var(--text-mid)", fontSize: 12,
      }}>
        <Icon name="bulb" size={14} />
        <span>{EFFORT_PARAMS[effort].label}</span>
      </button>
      {open && (
        <div style={{
          position: "absolute", bottom: "calc(100% + 8px)", right: 0, width: 300,
          background: "var(--surface)", border: "1px solid var(--border2)", borderRadius: 14,
          padding: "14px 16px 12px", boxShadow: "0 12px 40px rgba(0,0,0,0.5)", zIndex: 50,
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 12, fontSize: 12 }}>
            <span style={{ color: "var(--text-dim)" }}>intelligence</span>
            <span style={{ color: "var(--accent)", fontWeight: 600 }}>{EFFORT_PARAMS[effort].label}</span>
          </div>
          <div style={{ position: "relative", height: 30, margin: "0 4px" }}>
            <div style={{ position: "absolute", inset: 0, background: "var(--bg2)", borderRadius: 10 }} />
            {EFFORT_LEVELS.map((l, i) => (
              <div key={l} style={{ position: "absolute", left: at(i), top: 13, width: 3, height: 3, marginLeft: -1, borderRadius: "50%", background: "var(--text-dim)" }} />
            ))}
            <div style={{
              position: "absolute", left: at(idx), top: 0, width: 18, height: 30, marginLeft: -9, borderRadius: 9,
              background: "var(--text)", boxShadow: "0 1px 6px rgba(0,0,0,0.5)", pointerEvents: "none",
            }} />
            <input
              type="range" min={0} max={last} step={1} value={idx} aria-label="effort"
              onChange={e => onChange(EFFORT_LEVELS[+e.target.value])}
              style={{ position: "absolute", inset: 0, width: "100%", height: "100%", opacity: 0, margin: 0, cursor: "pointer" }}
            />
          </div>
          <div style={{ position: "relative", height: 18, margin: "8px 4px 0" }}>
            {EFFORT_LEVELS.map((l, i) => (
              <div key={l} style={{ position: "absolute", left: at(i), transform: "translateX(-50%)", textAlign: "center", fontSize: 11, whiteSpace: "nowrap", color: l === effort ? "var(--text)" : "var(--text-dim)" }}>
                <div>{EFFORT_PARAMS[l].short}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
