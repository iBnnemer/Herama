import { useEffect, useRef, useState } from "react";
import Icon from "./Icons";

export interface DropItem { id: string; label: string; hint?: string }

interface Props {
  label: string;
  items: DropItem[];
  value: string;
  onPick: (id: string) => void;
  icon?: React.ReactNode;
  tinted?: boolean;
  down?: boolean;
  align?: "left" | "right";
  title?: string;
}

/** Small pill button that opens a list of choices above (or below) it. */
export default function Dropdown({ label, items, value, onPick, icon, tinted, down, align = "left", title }: Props) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const h = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    window.addEventListener("mousedown", h);
    return () => window.removeEventListener("mousedown", h);
  }, [open]);

  return (
    <div ref={box} style={{ position: "relative" }}>
      <button onClick={() => setOpen(o => !o)} title={title} style={{
        display: "flex", alignItems: "center", gap: 6, padding: "5px 10px", borderRadius: 8, fontSize: 12,
        background: tinted ? "color-mix(in srgb, var(--accent) 16%, transparent)" : "transparent",
        color: tinted ? "var(--accent)" : "var(--text-mid)", border: "none", maxWidth: 220,
      }}>
        {icon}
        <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{label}</span>
        {!tinted && <Icon name="chevron" size={12} />}
      </button>
      {open && (
        <div style={{
          position: "absolute", [down ? "top" : "bottom"]: "calc(100% + 6px)", [align]: 0, minWidth: 220, maxHeight: 320, overflowY: "auto",
          background: "var(--surface)", border: "1px solid var(--border2)", borderRadius: 12, padding: 6,
          boxShadow: "0 12px 40px rgba(0,0,0,0.5)", zIndex: 50,
        }}>
          {items.length === 0 && <div style={{ padding: "8px 10px", fontSize: 12, color: "var(--text-dim)" }}>nothing here yet</div>}
          {items.map(it => (
            <button key={it.id} onClick={() => { onPick(it.id); setOpen(false); }} style={{
              display: "block", width: "100%", textAlign: "left", padding: "7px 10px", borderRadius: 8, fontSize: 13,
              background: it.id === value ? "var(--surface2)" : "transparent", color: "var(--text)",
            }}>
              <div>{it.label}</div>
              {it.hint && <div style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 1 }}>{it.hint}</div>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
