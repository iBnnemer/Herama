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
const KV_TYPES = ["f16", "q8_0", "q4_0"];

function fmtCtx(n: number) { return n >= 1024 ? `${(n / 1024).toFixed(0)}K` : String(n); }

const num: React.CSSProperties = {
  width: 70, background: "var(--bg2)", border: "1px solid var(--border)", borderRadius: 6,
  padding: "4px 8px", color: "var(--text)", fontSize: 13, textAlign: "right",
};

interface Edit { ngl?: number; cpuMoe?: number; topK?: number; kv?: string; threads?: number }

export default function SettingsModal({ model, contextLength, tps, onApply, onClose }: Props) {
  const [idx, setIdx] = useState(() => {
    const i = CTX_STEPS.findIndex(v => v >= contextLength);
    return i < 0 ? CTX_STEPS.length - 1 : i;
  });
  const [plan, setPlan] = useState<TunePlan | null>(null);
  const [manual, setManual] = useState(false);
  const [edit, setEdit] = useState<Edit>({});
  const [error, setError] = useState("");
  const ctx = CTX_STEPS[idx];

  useEffect(() => {
    if (!model) return;
    let live = true;
    const t = setTimeout(() => {
      const m = manual ? edit : {};
      fetchTune(model, ctx, m.ngl, m.cpuMoe, m.topK, m.kv)
        .then(p => { if (live) { setPlan(p); setError(""); } })
        .catch(e => { if (live) { setPlan(null); setError(String(e.message ?? e)); } });
    }, 250);
    return () => { live = false; clearTimeout(t); };
  }, [model, ctx, manual, edit]);

  const toggleManual = (on: boolean) => {
    setManual(on);
    // start from what the automatic layout would use, then let the user change it
    setEdit(on && plan ? { ngl: plan.ngl, cpuMoe: plan.cpu_moe, topK: plan.top_k, kv: plan.kv_type } : {});
  };

  const apply = () => {
    if (manual && plan) {
      onApply(ctx, {
        ctx, numGpu: plan.ngl, cpuMoe: plan.cpu_moe, kvType: plan.kv_type, threads: edit.threads ?? 0,
        expertUsed: plan.default_top_k && plan.top_k !== plan.default_top_k ? plan.top_k : 0,
      });
    } else {
      onApply(plan && !plan.manual ? plan.ctx : ctx);  // automatic: the layout is chosen by the engine when the model loads
    }
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
        <div style={{ marginBottom: 16, padding: "12px", background: "var(--bg2)", borderRadius: 8, fontSize: 12, color: "var(--text-mid)" }}>
          <div style={{ color: "var(--text-dim)", marginBottom: 8 }}>
            {manual ? "Manual layout. These values are used exactly as set." : "Chosen automatically for this model and context."}
          </div>
          {manual ? (
            <>
              <Row label="GPU layers" hint={`of ${plan.layers}`}>
                <input type="number" min={0} max={plan.layers} style={num} value={plan.ngl}
                  onChange={e => setEdit(v => ({ ...v, ngl: Math.max(0, Math.min(plan.layers, +e.target.value || 0)) }))} />
              </Row>
              {plan.moe && (
                <Row label="Expert layers on CPU" hint={`of ${plan.layers}`}>
                  <input type="number" min={0} max={plan.layers} style={num} value={plan.cpu_moe}
                    onChange={e => setEdit(v => ({ ...v, cpuMoe: Math.max(0, Math.min(plan.layers, +e.target.value || 0)) }))} />
                </Row>
              )}
              {plan.moe && plan.default_top_k > 0 && (
                <Row label="Active experts per token" hint={`model default ${plan.default_top_k}`}>
                  <input type="number" min={1} max={plan.experts} style={num} value={plan.top_k}
                    onChange={e => setEdit(v => ({ ...v, topK: Math.max(1, Math.min(plan.experts, +e.target.value || 1)) }))} />
                </Row>
              )}
              <Row label="KV cache type">
                <select value={plan.kv_type} onChange={e => setEdit(v => ({ ...v, kv: e.target.value }))}
                  style={{ ...num, width: 90, textAlign: "left" }}>
                  {KV_TYPES.map(k => <option key={k} value={k}>{k}</option>)}
                </select>
              </Row>
              <Row label="CPU threads" hint="0 = automatic">
                <input type="number" min={0} max={256} style={num} value={edit.threads ?? 0}
                  onChange={e => setEdit(v => ({ ...v, threads: Math.max(0, +e.target.value || 0) }))} />
              </Row>
              {plan.moe && plan.top_k < plan.default_top_k && (
                <div style={{ color: "var(--accent)", margin: "2px 0 4px" }}>Fewer active experts is faster but lowers answer quality.</div>
              )}
            </>
          ) : (
            <>
              <Row label="GPU layers">{plan.ngl} of {plan.layers}</Row>
              {plan.moe && <Row label="Expert layers on CPU">{plan.cpu_moe} of {plan.layers}</Row>}
              <Row label="KV cache type">{plan.kv_type}</Row>
            </>
          )}
          <Row label="KV cache size">{plan.kv_gb} GB</Row>
          <Row label="GPU memory" hint={`budget ${plan.vram_budget_gb} GB`}>{plan.vram_gb} GB</Row>
          <Row label="System RAM">{plan.ram_gb} GB</Row>
          <Row label={plan.calibrated === "measured" ? "Measured speed" : plan.calibrated === "learned" ? "Estimated speed (adjusted from your runs)" : "Estimated speed"}>
            <span style={{ color: "var(--text)", fontWeight: 600 }}>{plan.calibrated === "measured" ? "" : "about "}{plan.tps} tok/s</span>
          </Row>
          {!manual && plan.adjusted.length > 0 && (
            <div style={{ marginTop: 8 }}>
              <div style={{ color: "var(--text)", fontWeight: 600, marginBottom: 2 }}>Adjusted automatically</div>
              {plan.adjusted.map(a => <div key={a}>{a}</div>)}
            </div>
          )}
          {!plan.fits && <div style={{ color: "var(--red)", marginTop: 6 }}>These numbers exceed this machine's memory.</div>}
          {plan.ctx_over_training && <div style={{ color: "var(--red)", marginTop: 6 }}>This context is larger than the model was trained for ({fmtCtx(plan.ctx_train)}). Longer contexts usually degrade.</div>}
        </div>
      )}
      {!plan && error && <div style={{ marginBottom: 16, fontSize: 12, color: "var(--text-dim)" }}>No estimate available ({error}). Only the context length will change.</div>}

      <label style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 13, color: "var(--text-mid)", marginBottom: 16, cursor: "pointer" }}>
        <input type="checkbox" checked={manual} onChange={e => toggleManual(e.target.checked)} /> Manual tuning
      </label>

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
