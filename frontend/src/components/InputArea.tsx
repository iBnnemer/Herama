import { useRef, KeyboardEvent, useState } from "react";
import type { Effort, Model } from "../types";
import { EFFORT_PARAMS } from "../types";
import SettingsModal from "./SettingsModal";

interface Props {
  models: Model[];
  activeModel: string;
  effort: Effort;
  contextLength: number;
  tps: number;
  onSend: (text: string) => void;
  onModelChange: (m: string) => void;
  onEffortChange: (e: Effort) => void;
  onContextChange: (n: number) => void;
  disabled: boolean;
  placeholder?: string;
}

const EFFORTS: Effort[] = ["fast", "balanced", "smart"];

export default function InputArea(p: Props) {
  const ref = useRef<HTMLTextAreaElement>(null);
  const [showSettings, setShowSettings] = useState(false);

  const send = () => {
    const v = ref.current?.value.trim();
    if (!v || p.disabled) return;
    p.onSend(v);
    if (ref.current) { ref.current.value = ""; ref.current.style.height = "auto"; }
  };

  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
  };

  return (
    <div style={{
      padding: "0 16px 16px", flexShrink: 0,
      maxWidth: 760, width: "100%", margin: "0 auto",
    }}>
      {/* Textarea */}
      <div style={{
        background: "var(--surface)", border: "1px solid var(--border2)",
        borderRadius: 14, overflow: "hidden",
        boxShadow: "0 2px 12px rgba(0,0,0,0.3)",
      }}>
        <textarea
          ref={ref}
          disabled={p.disabled}
          placeholder={p.placeholder ?? "message herama…"}
          rows={1}
          onKeyDown={onKey}
          onInput={e => {
            const t = e.currentTarget;
            t.style.height = "auto";
            t.style.height = Math.min(t.scrollHeight, 180) + "px";
          }}
          style={{
            width: "100%", padding: "14px 50px 14px 16px",
            fontSize: 14, lineHeight: 1.5, minHeight: 50,
            maxHeight: 180, background: "transparent",
            color: "var(--text)", opacity: p.disabled ? 0.5 : 1,
          }}
        />
        {/* Send button inside box */}
        <button
          onClick={send}
          disabled={p.disabled}
          style={{
            position: "absolute", right: 28, bottom: 80,
            width: 30, height: 30, borderRadius: "50%",
            background: p.disabled ? "var(--border)" : "var(--accent)",
            color: p.disabled ? "var(--text-dim)" : "#000",
            fontSize: 14, display: "flex", alignItems: "center", justifyContent: "center",
          }}
        >↑</button>
      </div>

      {/* Controls bar below textarea */}
      <div style={{
        display: "flex", alignItems: "center", gap: 8, marginTop: 8,
        padding: "0 4px",
      }}>
        {/* Model selector */}
        <select
          value={p.activeModel}
          onChange={e => p.onModelChange(e.target.value)}
          style={{
            background: "var(--surface)", border: "1px solid var(--border)",
            borderRadius: 8, padding: "4px 8px", color: "var(--text-mid)",
            fontSize: 12, cursor: "pointer", fontFamily: "var(--sans)",
            maxWidth: 160, overflow: "hidden", textOverflow: "ellipsis",
          }}
        >
          {p.models.length === 0 && <option value="">no models</option>}
          {p.models.map(m => <option key={m.name} value={m.name}>{m.name}</option>)}
        </select>

        {/* Effort pills */}
        <div style={{ display: "flex", gap: 3, background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, padding: 3 }}>
          {EFFORTS.map(e => (
            <button
              key={e}
              onClick={() => p.onEffortChange(e)}
              style={{
                padding: "3px 10px", borderRadius: 6, fontSize: 11,
                background: p.effort === e ? "var(--surface2)" : "transparent",
                color: p.effort === e ? "var(--text)" : "var(--text-dim)",
                fontWeight: p.effort === e ? 600 : 400,
                border: p.effort === e ? "1px solid var(--border2)" : "1px solid transparent",
              }}
            >{EFFORT_PARAMS[e].label}</button>
          ))}
        </div>

        {/* Settings */}
        <button
          onClick={() => setShowSettings(true)}
          style={{ padding: "4px 8px", background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, color: "var(--text-dim)", fontSize: 12 }}
        >⚙</button>

        {/* Token hint */}
        <span style={{ marginLeft: "auto", fontSize: 10, color: "var(--text-dim)" }}>
          ctx {p.contextLength >= 1024 ? `${(p.contextLength / 1024).toFixed(0)}K` : p.contextLength}
        </span>
      </div>

      {showSettings && (
        <SettingsModal
          contextLength={p.contextLength}
          tps={p.tps}
          onApply={p.onContextChange}
          onClose={() => setShowSettings(false)}
        />
      )}
    </div>
  );
}
