import { useEffect, useRef, useState } from "react";
import type { Model } from "../types";
import { fetchTune } from "../api";
import Icon from "./Icons";

interface Props {
  models: Model[];
  active: string;
  contextLength: number;
  onPick: (name: string) => void;
  onManage: () => void;
}

const stem = (n: string) => n.replace(/:latest$/, "");
const QUANT = /[-_.](i?q\d[\w]*|f16|f32|bf16)$/i;
const title = (n: string) => stem(n).replace(QUANT, "");
const ctxLabel = (n: number) => (n >= 1024 ? `${Math.round(n / 1024)}K` : String(n));

/** Model chooser: lists local models with size and an estimated speed at the current context. */
export default function ModelPicker({ models, active, contextLength, onPick, onManage }: Props) {
  const [open, setOpen] = useState(false);
  const [speed, setSpeed] = useState<Record<string, number>>({});
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const h = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    window.addEventListener("mousedown", h);
    return () => window.removeEventListener("mousedown", h);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    let live = true;
    setSpeed({});
    models.forEach(m => {
      fetchTune(m.name, contextLength).then(t => { if (live) setSpeed(s => ({ ...s, [m.name]: t.tps })); }).catch(() => {});
    });
    return () => { live = false; };
  }, [open, models, contextLength]);

  return (
    <div ref={box} style={{ position: "relative" }}>
      <button onClick={() => setOpen(o => !o)} style={{
        display: "flex", alignItems: "center", gap: 6, padding: "5px 8px", fontSize: 14,
        color: "var(--text)", background: "transparent", border: "none", borderRadius: 8, maxWidth: 320,
      }}>
        <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{active ? title(active) : "Choose a model"}</span>
        <Icon name="chevron" size={13} />
      </button>
      {open && (
        <div style={{
          position: "absolute", bottom: "calc(100% + 8px)", right: 0, width: 520, maxWidth: "92vw", maxHeight: "70vh", overflowY: "auto",
          background: "var(--surface)", border: "1px solid var(--border2)", borderRadius: 14, padding: "14px 8px 8px",
          boxShadow: "0 12px 40px rgba(0,0,0,0.55)", zIndex: 60,
        }}>
          <div style={{ padding: "0 12px 10px" }}>
            <div style={{ fontSize: 13, color: "var(--text-mid)" }}>Models on this PC</div>
            <div style={{ fontSize: 12, color: "var(--text-dim)", marginTop: 4 }}>Speeds estimated at {ctxLabel(contextLength)} context</div>
          </div>
          {models.length === 0 && <div style={{ padding: "8px 12px", fontSize: 13, color: "var(--text-dim)" }}>No models found.</div>}
          {models.map(m => (
            <button key={m.name} onClick={() => { onPick(m.name); setOpen(false); }} style={{
              display: "flex", alignItems: "center", gap: 12, width: "100%", textAlign: "left", padding: "10px 12px", borderRadius: 10,
              background: m.name === active ? "var(--surface2)" : "transparent", color: "var(--text)",
            }}>
              <span style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 14, fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{title(m.name)}</div>
                <div style={{ fontSize: 11, color: "var(--text-dim)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{stem(m.name)}</div>
              </span>
              <span style={{ fontSize: 12, color: "var(--text-dim)", whiteSpace: "nowrap" }}>
                {m.size ? `${(m.size / 1e9).toFixed(2)} GB` : ""}{speed[m.name] ? ` · ≈ ${speed[m.name].toFixed(1)} tok/s` : ""}
              </span>
            </button>
          ))}
          <div style={{ borderTop: "1px solid var(--border)", margin: "8px 4px 0", paddingTop: 4 }}>
            <button onClick={() => { setOpen(false); onManage(); }} style={{ padding: "10px 8px", fontSize: 13, color: "var(--text)", background: "transparent" }}>Manage models...</button>
          </div>
        </div>
      )}
    </div>
  );
}
