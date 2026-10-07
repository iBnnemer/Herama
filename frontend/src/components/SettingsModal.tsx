import Modal from "./Modal";
import { useState } from "react";

interface Props {
  contextLength: number;
  tps: number;
  onApply: (ctx: number) => void;
  onClose: () => void;
}

const CTX_STEPS = [512, 1024, 2048, 4096, 8192, 16384, 32768, 65536, 131072, 262144];

export default function SettingsModal({ contextLength, tps, onApply, onClose }: Props) {
  const [idx, setIdx] = useState(() => {
    const i = CTX_STEPS.findIndex(v => v >= contextLength);
    return i < 0 ? CTX_STEPS.length - 1 : i;
  });

  const val = CTX_STEPS[idx];

  return (
    <Modal title="model settings" onClose={onClose}>
      <Row label="context length">
        <input
          type="range" min={0} max={CTX_STEPS.length - 1}
          value={idx} onChange={e => setIdx(+e.target.value)}
          style={{ width: "100%", accentColor: "var(--accent)" }}
        />
        <span style={{ color: "var(--accent)", fontSize: 12 }}>
          {val >= 1024 ? `${(val / 1024).toFixed(0)}K` : val} tokens
        </span>
      </Row>
      {tps > 0 && (
        <Row label="speed">
          <span style={{ color: "var(--text-mid)", fontSize: 12 }}>{tps.toFixed(1)} t/s</span>
        </Row>
      )}
      <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 16 }}>
        <button onClick={onClose} style={{ padding: "6px 14px", border: "1px solid var(--border)", borderRadius: 4, color: "var(--text-mid)", fontSize: 12 }}>cancel</button>
        <button onClick={() => { onApply(val); onClose(); }} style={{ padding: "6px 14px", background: "var(--accent)", color: "#000", borderRadius: 4, fontWeight: 600, fontSize: 12 }}>apply</button>
      </div>
    </Modal>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ color: "var(--text-dim)", fontSize: 10, marginBottom: 6, letterSpacing: "0.08em" }}>{label}</div>
      {children}
    </div>
  );
}
