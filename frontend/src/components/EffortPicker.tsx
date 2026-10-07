import { useEffect, useRef, useState } from "react";
import type { Effort } from "../types";
import { EFFORT_LEVELS, EFFORT_PARAMS } from "../types";
import Icon from "./Icons";

interface Props { effort: Effort; onChange: (e: Effort) => void }

export default function EffortPicker({ effort, onChange }: Props) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const idx = EFFORT_LEVELS.indexOf(effort);

  useEffect(() => {
    if (!open) return;
    const h = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    window.addEventListener("mousedown", h);
    return () => window.removeEventListener("mousedown", h);
  }, [open]);

  return (
    <div ref={box} style={{ position: "relative" }}>
      <button onClick={() => setOpen(o => !o)} style={{
        display: "flex", alignItems: "center", gap: 5, padding: "4px 10px",
        background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8,
        color: "var(--text-mid)", fontSize: 12,
      }}>
        <span>{EFFORT_PARAMS[effort].label}</span>
        <Icon name="chevron" size={12} />
      </button>
      {open && (
        <div style={{
          position: "absolute", bottom: "calc(100% + 8px)", left: 0, width: 260,
          background: "var(--surface)", border: "1px solid var(--border2)", borderRadius: 12,
          padding: "14px 16px", boxShadow: "0 12px 40px rgba(0,0,0,0.5)", zIndex: 50,
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 10, fontSize: 12 }}>
            <span style={{ color: "var(--text-dim)" }}>intelligence</span>
            <span style={{ color: "var(--accent)", fontWeight: 600 }}>{EFFORT_PARAMS[effort].label}</span>
          </div>
          <input
            type="range" min={0} max={EFFORT_LEVELS.length - 1} step={1} value={idx}
            onChange={e => onChange(EFFORT_LEVELS[+e.target.value])}
            style={{ width: "100%", accentColor: "var(--accent)", cursor: "pointer" }}
          />
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--text-dim)", marginTop: 4 }}>
            {EFFORT_LEVELS.map(l => (
              <span key={l} style={{ color: l === effort ? "var(--text)" : "var(--text-dim)" }}>{EFFORT_PARAMS[l].short}</span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
