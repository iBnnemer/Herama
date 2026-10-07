import { useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import type { Effort, Model } from "../types";
import EffortPicker from "./EffortPicker";
import SettingsModal from "./SettingsModal";
import Icon from "./Icons";

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

const shortName = (n: string) => n.replace(/:latest$/, "");

export default function InputArea(p: Props) {
  const ref = useRef<HTMLTextAreaElement>(null);
  const [showSettings, setShowSettings] = useState(false);
  const [hasText, setHasText] = useState(false);

  const send = () => {
    const v = ref.current?.value.trim();
    if (!v || p.disabled) return;
    p.onSend(v);
    if (ref.current) { ref.current.value = ""; ref.current.style.height = "auto"; }
    setHasText(false);
  };

  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send(); }
  };

  const canSend = hasText && !p.disabled;
  const chip: React.CSSProperties = {
    background: "transparent", border: "none", borderRadius: 8, padding: "4px 8px",
    color: "var(--text-mid)", fontSize: 12, cursor: "pointer",
  };

  return (
    <div style={{ padding: "0 16px 18px", flexShrink: 0, maxWidth: 780, width: "100%", margin: "0 auto" }}>
      <div style={{
        background: "var(--surface)", border: "1px solid var(--border2)", borderRadius: 18,
        boxShadow: "0 2px 12px rgba(0,0,0,0.3)", padding: "10px 10px 8px 14px",
      }}>
        <textarea
          ref={ref}
          dir="auto"
          placeholder={p.placeholder ?? "message herama..."}
          rows={1}
          onKeyDown={onKey}
          onInput={e => {
            const t = e.currentTarget;
            t.style.height = "auto";
            t.style.height = Math.min(t.scrollHeight, 200) + "px";
            setHasText(t.value.trim().length > 0);
          }}
          style={{
            width: "100%", padding: "6px 4px", fontSize: 15, lineHeight: 1.5, minHeight: 32,
            maxHeight: 200, background: "transparent", color: "var(--text)", display: "block",
          }}
        />
        <div style={{ display: "flex", alignItems: "center", gap: 4, marginTop: 4 }}>
          <button onClick={() => setShowSettings(true)} title="generation settings"
            style={{ ...chip, display: "flex", padding: 6 }}><Icon name="gear" size={15} /></button>

          <select
            value={p.activeModel}
            onChange={e => p.onModelChange(e.target.value)}
            style={{ ...chip, maxWidth: 240, textOverflow: "ellipsis", fontFamily: "var(--sans)" }}
          >
            {p.models.length === 0 && <option value="">no models</option>}
            {p.models.map(m => <option key={m.name} value={m.name} style={{ background: "var(--surface)" }}>{shortName(m.name)}</option>)}
          </select>

          <EffortPicker effort={p.effort} onChange={p.onEffortChange} />

          <span style={{ marginLeft: "auto", marginRight: 8, fontSize: 10, color: "var(--text-dim)" }}>
            ctx {p.contextLength >= 1024 ? `${Math.round(p.contextLength / 1024)}K` : p.contextLength}
          </span>

          <button onClick={send} disabled={!canSend} title="send" style={{
            width: 32, height: 32, borderRadius: 10, flexShrink: 0,
            background: canSend ? "var(--accent)" : "var(--surface2)",
            color: canSend ? "#000" : "var(--text-dim)",
            display: "flex", alignItems: "center", justifyContent: "center",
          }}><Icon name="send" size={16} /></button>
        </div>
      </div>

      {showSettings && (
        <SettingsModal contextLength={p.contextLength} tps={p.tps} onApply={p.onContextChange} onClose={() => setShowSettings(false)} />
      )}
    </div>
  );
}
