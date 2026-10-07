import Modal from "./Modal";
import { useState } from "react";

interface Props {
  contextLength: number;
  tps: number;
  onApply: (ctx: number) => void;
  onClose: () => void;
}

const CTX_STEPS = [512, 1024, 2048, 4096, 8192, 16384, 32768, 65536, 131072, 262144];

function fmtCtx(n: number) { return n >= 1024 ? `${(n / 1024).toFixed(0)}K` : String(n); }

export default function SettingsModal({ contextLength, tps, onApply, onClose }: Props) {
  const [idx, setIdx] = useState(() => {
    const i = CTX_STEPS.findIndex(v => v >= contextLength);
    return i < 0 ? CTX_STEPS.length - 1 : i;
  });

  return (
    <Modal title="generation settings" onClose={onClose}>
      <div style={{ marginBottom: 20 }}>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8, fontSize: 12 }}>
          <span style={{ color: "var(--text-dim)" }}>context length</span>
          <span style={{ color: "var(--accent)", fontWeight: 600 }}>{fmtCtx(CTX_STEPS[idx])} tokens</span>
        </div>
        <input
          type="range" min={0} max={CTX_STEPS.length - 1}
          value={idx} onChange={e => setIdx(+e.target.value)}
          style={{ width: "100%", accentColor: "var(--accent)", cursor: "pointer" }}
        />
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--text-dim)", marginTop: 4 }}>
          <span>512</span><span>262K</span>
        </div>
      </div>
      {tps > 0 && (
        <div style={{ marginBottom: 20, padding: "10px 12px", background: "var(--bg2)", borderRadius: 8, fontSize: 12, color: "var(--text-mid)" }}>
          last speed: <span style={{ color: "var(--text)" }}>{tps.toFixed(1)} tokens/s</span>
        </div>
      )}
      <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
        <button onClick={onClose} style={{ padding: "7px 16px", border: "1px solid var(--border)", borderRadius: 8, color: "var(--text-mid)", fontSize: 13 }}>cancel</button>
        <button onClick={() => { onApply(CTX_STEPS[idx]); onClose(); }} style={{ padding: "7px 16px", background: "var(--accent)", color: "#000", borderRadius: 8, fontWeight: 600, fontSize: 13 }}>apply</button>
      </div>
    </Modal>
  );
}
