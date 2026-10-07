import { useState } from "react";
import type { Model } from "../types";
import SettingsModal from "./SettingsModal";

interface Props {
  models: Model[];
  activeModel: string;
  contextLength: number;
  tps: number;
  onModelChange: (m: string) => void;
  onContextChange: (n: number) => void;
  tokenCount: number;
}

const S: Record<string, React.CSSProperties> = {
  bar: {
    display: "flex", alignItems: "center", gap: 8,
    padding: "6px 16px", borderTop: "1px solid var(--border)",
    background: "var(--surface)", flexShrink: 0,
  },
  label: { color: "var(--text-dim)", fontSize: 11 },
  select: {
    background: "var(--surface2)", border: "1px solid var(--border)", borderRadius: 4,
    color: "var(--text)", padding: "3px 6px", fontSize: 11, cursor: "pointer",
    fontFamily: "var(--mono)",
  },
  btn: {
    padding: "3px 8px", border: "1px solid var(--border)",
    borderRadius: 4, color: "var(--text-dim)", fontSize: 11,
    background: "var(--surface2)",
  },
  tokens: { marginLeft: "auto", color: "var(--text-dim)", fontSize: 10 },
};

export default function ModelBar({ models, activeModel, contextLength, tps, onModelChange, onContextChange, tokenCount }: Props) {
  const [showSettings, setShowSettings] = useState(false);

  return (
    <>
      <div style={S.bar}>
        <span style={S.label}>model:</span>
        <select
          style={S.select}
          value={activeModel}
          onChange={e => onModelChange(e.target.value)}
        >
          {models.length === 0 && <option value="">— no models —</option>}
          {models.map(m => <option key={m.name} value={m.name}>{m.name}</option>)}
        </select>
        <button style={S.btn} onClick={() => setShowSettings(true)}>⚙ settings</button>
        <span style={S.tokens}>{tokenCount > 0 ? `${tokenCount} tokens` : ""}</span>
      </div>
      {showSettings && (
        <SettingsModal
          contextLength={contextLength}
          tps={tps}
          onApply={onContextChange}
          onClose={() => setShowSettings(false)}
        />
      )}
    </>
  );
}
