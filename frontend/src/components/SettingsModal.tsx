import Modal from "./Modal";
import { useEffect, useState } from "react";
import { fetchTune } from "../api";
import type { TunePlan } from "../api";
import type { Tune } from "../types";

interface Props {
  model: string;
  contextLength: number;
  tps: number;
  onApply: (ctx: number, tune?: Tune) => void;
  onClose: () => void;
}

const CTX_STEPS = [512, 1024, 2048, 4096, 8192, 16384, 32768, 65536, 131072, 262144];

function fmtCtx(n: number) { return n >= 1024 ? `${(n / 1024).toFixed(0)}K` : String(n); }

const num: React.CSSProperties = {
  width: 70, background: "var(--bg2)", border: "1px solid var(--border)", borderRadius: 6,
  padding: "4px 8px", color: "var(--text)", fontSize: 13, textAlign: "right",
};

export default function SettingsModal({ model, contextLength, tps, onApply, onClose }: Props) {
  const [idx, setIdx] = useState(() => {
    const i = CTX_STEPS.findIndex(v => v >= contextLength);
    return i < 0 ? CTX_STEPS.length - 1 : i;
  });
  const [plan, setPlan] = useState<TunePlan | null>(null);
  const [edit, setEdit] = useState<{ ngl?: number; cpuMoe?: number }>({});
  const [error, setError] = useState("");
  const ctx = CTX_STEPS[idx];

  // a new context length starts from a fresh proposal; edited numbers re-estimate it
  useEffect(() => { setEdit({}); }, [ctx]);
  useEffect(() => {
    if (!model) return;
    let live = true;
    const t = setTimeout(() => {
      fetchTune(model, ctx, edit.ngl, edit.cpuMoe)
        .then(p => { if (live) { setPlan(p); setError(""); } })
        .catch(e => { if (live) { setPlan(null); setError(String(e.message ?? e)); } });
    }, 250);
    return () => { live = false; clearTimeout(t); };
  }, [model, ctx, edit]);

  const apply = () => {
    onApply(ctx, plan ? { ctx, numGpu: plan.ngl, cpuMoe: plan.cpu_moe } : undefined);
    onClose();
  };

  return (
    <Modal title="generation settings" onClose={onClose}>
      <div style={{ marginBottom: 20 }}>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8, fontSize: 12 }}>
          <span style={{ color: "var(--text-dim)" }}>context length</span>
          <span style={{ color: "var(--accent)", fontWeight: 600 }}>{fmtCtx(ctx)} tokens</span>
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

      {plan && (
        <div style={{ marginBottom: 20, padding: "12px", background: "var(--bg2)", borderRadius: 8, fontSize: 12, color: "var(--text-mid)" }}>
          <div style={{ color: "var(--text-dim)", marginBottom: 8 }}>
            Preliminary settings for this context. Nothing changes until you press apply.
          </div>
          <Row label="GPU layers" hint={`of ${plan.layers}`}>
            <input type="number" min={0} max={plan.layers} style={num} value={plan.ngl}
              onChange={e => setEdit(v => ({ ...v, ngl: Math.max(0, Math.min(plan.layers, +e.target.value || 0)), cpuMoe: v.cpuMoe ?? plan.cpu_moe }))} />
          </Row>
          {plan.moe && (
            <Row label="MoE layers with experts on CPU" hint={`of ${plan.layers}, ${plan.experts} experts per layer`}>
              <input type="number" min={0} max={plan.layers} style={num} value={plan.cpu_moe}
                onChange={e => setEdit(v => ({ ...v, cpuMoe: Math.max(0, Math.min(plan.layers, +e.target.value || 0)), ngl: v.ngl ?? plan.ngl }))} />
            </Row>
          )}
          <Row label="KV cache">{plan.kv_gb} GB</Row>
          <Row label="GPU memory" hint={`budget ${plan.vram_budget_gb} GB`}>{plan.vram_gb} GB</Row>
          <Row label="System RAM">{plan.ram_gb} GB</Row>
          <Row label="Estimated speed"><span style={{ color: "var(--text)", fontWeight: 600 }}>about {plan.tps} tok/s</span></Row>
          {!plan.fits && <div style={{ color: "var(--red)", marginTop: 6 }}>These numbers exceed this machine's memory. Lower the context or move more layers to the CPU.</div>}
          {plan.ctx_over_training && <div style={{ color: "var(--red)", marginTop: 6 }}>This context is larger than the model was trained for ({fmtCtx(plan.ctx_train)}). Quality may drop.</div>}
        </div>
      )}
      {!plan && error && <div style={{ marginBottom: 16, fontSize: 12, color: "var(--text-dim)" }}>No estimate available ({error}). Only the context length will change.</div>}

      {tps > 0 && (
        <div style={{ marginBottom: 20, padding: "10px 12px", background: "var(--bg2)", borderRadius: 8, fontSize: 12, color: "var(--text-mid)" }}>
          last speed: <span style={{ color: "var(--text)" }}>{tps.toFixed(1)} tokens/s</span>
        </div>
      )}
      <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
        <button onClick={onClose} style={{ padding: "7px 16px", border: "1px solid var(--border)", borderRadius: 8, color: "var(--text-mid)", fontSize: 13 }}>cancel</button>
        <button onClick={apply} style={{ padding: "7px 16px", background: "var(--accent)", color: "#000", borderRadius: 8, fontWeight: 600, fontSize: 13 }}>apply</button>
      </div>
    </Modal>
  );
}

function Row({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, padding: "3px 0" }}>
      <span>{label}{hint && <span style={{ color: "var(--text-dim)" }}> ({hint})</span>}</span>
      <span>{children}</span>
    </div>
  );
}
