import { useEffect, useState } from "react";
import { fetchMonitor } from "../api";
import type { MonitorSnap, ModelStateName } from "../api";
import { STATE_COLORS } from "./StateDot";
import Icon from "./Icons";
import type { IconName } from "./Icons";

const HISTORY = 60;
const PILLS: [ModelStateName, string][] = [["idle", "Idle"], ["reading", "Reading"], ["generating", "Generating"], ["queued", "Queued"], ["error", "Error"]];

interface Hist { decode: number[]; gpu: number[]; vram: number[]; temp: number[]; power: number[]; cpu: number[] }
const EMPTY: Hist = { decode: [], gpu: [], vram: [], temp: [], power: [], cpu: [] };
const push = (a: number[], v: number | undefined) => [...a, v ?? 0].slice(-HISTORY);

function Spark({ data, color, max }: { data: number[]; color: string; max?: number }) {
  if (data.length < 2) return <div style={{ height: 26 }} />;
  const hi = max ?? Math.max(1, ...data);
  const pts = data.map((v, i) => `${(i / (HISTORY - 1)) * 100},${26 - Math.min(1, v / hi) * 24}`).join(" ");
  return (
    <svg viewBox="0 0 100 26" preserveAspectRatio="none" style={{ width: "100%", height: 26, display: "block", marginTop: 8 }}>
      <polyline points={pts} fill="none" stroke={color} strokeWidth={1.2} vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

function Tile(p: { icon: IconName; title: string; children: React.ReactNode }) {
  return (
    <div style={{ background: "var(--bg2)", border: "1px solid var(--border)", borderRadius: 14, padding: "14px 16px", minHeight: 120 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "var(--text-mid)", marginBottom: 8 }}>
        <Icon name={p.icon} size={13} />{p.title}
      </div>
      {p.children}
    </div>
  );
}

const big: React.CSSProperties = { fontSize: 26, fontWeight: 700, lineHeight: 1.1 };
const unit: React.CSSProperties = { fontSize: 12, color: "var(--text-dim)", fontWeight: 400, marginLeft: 3 };
const sub: React.CSSProperties = { fontSize: 11, color: "var(--text-dim)", marginTop: 4 };
const val = (v: number | undefined, d = 0) => (v === undefined || v === null ? "-" : v.toFixed(d));

function Bar({ label, value, text, pct, color }: { label: string; value?: string; text?: string; pct: number; color: string }) {
  return (
    <div style={{ marginTop: 14 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
        <span style={{ fontWeight: 600 }}>{label}</span><span style={{ color: "var(--text-dim)" }}>{value ?? text ?? "-"}</span>
      </div>
      <div style={{ height: 7, background: "var(--surface2)", borderRadius: 4, marginTop: 6, overflow: "hidden" }}>
        <div style={{ width: `${Math.max(0, Math.min(100, pct))}%`, height: "100%", background: color, borderRadius: 4, transition: "width .4s" }} />
      </div>
    </div>
  );
}

const clock = (t: number) => new Date(t * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });

export default function MonitorModal({ onClose }: { onClose: () => void }) {
  const [snap, setSnap] = useState<MonitorSnap | null>(null);
  const [hist, setHist] = useState<Hist>(EMPTY);

  useEffect(() => {
    let live = true;
    const tick = async () => {
      const s = await fetchMonitor();
      if (!live || !s) return;
      setSnap(s);
      setHist(h => ({
        decode: push(h.decode, s.state.state === "generating" ? s.state.tps : h.decode[h.decode.length - 1] ?? 0),
        gpu: push(h.gpu, s.gpu.load), vram: push(h.vram, s.gpu.vram_used_mb), temp: push(h.temp, s.gpu.temp),
        power: push(h.power, s.gpu.power), cpu: push(h.cpu, s.system.cpu),
      }));
    };
    void tick();
    const t = setInterval(tick, 1000);
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", esc);
    return () => { live = false; clearInterval(t); window.removeEventListener("keydown", esc); };
  }, [onClose]);

  const st = snap?.state;
  const g = snap?.gpu ?? {};
  const sys = snap?.system ?? {};
  const color = STATE_COLORS[st?.state ?? "idle"];
  const status = !st ? "Connecting..." :
    st.state === "idle" ? "Waiting for a request" :
    st.state === "reading" ? `Reading the prompt ${Math.round(st.progress * 100)}%` :
    st.state === "generating" ? `Generating${st.tps ? ` at ${st.tps.toFixed(1)} tok/s` : ""}` :
    st.detail || (st.state === "queued" ? "Loading the model" : "Error");
  const ctxPct = snap && snap.ctx_total ? Math.min(100, (snap.ctx_used / snap.ctx_total) * 100) : 0;
  const R = 52, C = Math.PI * R;
  const vramGb = (g.vram_used_mb ?? 0) / 1024;

  return (
    <div onClick={e => { if (e.target === e.currentTarget) onClose(); }} style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,0.55)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center",
    }}>
      <div style={{
        width: "min(1000px, 94vw)", maxHeight: "88vh", overflowY: "auto", background: "var(--surface)",
        border: "1px solid var(--border2)", borderRadius: 16, boxShadow: "0 20px 60px rgba(0,0,0,0.6)",
      }}>
        <div style={{ display: "flex", alignItems: "center", padding: "16px 22px", borderBottom: "1px solid var(--border)" }}>
          <span style={{ fontWeight: 700, fontSize: 15 }}>Monitor</span>
          <button onClick={onClose} style={{ marginLeft: "auto", color: "var(--text-dim)", display: "flex" }}><Icon name="close" size={16} /></button>
        </div>
        <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 14 }}>
          <div style={{ background: "var(--bg2)", border: "1px solid var(--border)", borderRadius: 14, padding: "16px 18px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
              <span style={{ fontWeight: 700, fontSize: 15, marginRight: 6 }}>Model state</span>
              {PILLS.map(([id, label]) => {
                const on = st?.state === id;
                return (
                  <span key={id} style={{
                    fontSize: 11, padding: "3px 9px", borderRadius: 999, display: "flex", alignItems: "center", gap: 5,
                    background: on ? `color-mix(in srgb, ${STATE_COLORS[id]} 22%, transparent)` : "var(--surface2)",
                    color: on ? STATE_COLORS[id] : "var(--text-dim)", opacity: on ? 1 : 0.7,
                  }}><span style={{ width: 6, height: 6, borderRadius: "50%", background: STATE_COLORS[id] }} />{label}</span>
                );
              })}
            </div>
            <div style={{ fontSize: 12, fontWeight: 600, margin: "12px 0 10px" }}>{status}</div>
            <div style={{ height: 6, background: "var(--surface2)", borderRadius: 4, overflow: "hidden" }}>
              <div style={{
                height: "100%", background: color, borderRadius: 4, transition: "width .3s",
                width: st?.state === "reading" ? `${st.progress * 100}%` : st && st.state !== "idle" ? "100%" : "0%",
                animation: st?.state === "queued" || st?.state === "generating" ? "herama-pulse 1.2s ease-in-out infinite" : undefined,
              }} />
            </div>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))", gap: 12 }}>
            <Tile icon="gauge" title="Speed">
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <div><div style={big}>{snap?.decode_tps ? snap.decode_tps.toFixed(1) : "-"}</div><div style={sub}>Decode tok/s</div></div>
                <div style={{ textAlign: "right" }}><div style={big}>{snap?.prefill_tps ? snap.prefill_tps.toFixed(0) : "-"}</div><div style={sub}>Prefill tok/s</div></div>
              </div>
              <Spark data={hist.decode} color="var(--accent)" />
            </Tile>
            <Tile icon="box" title="GPU load">
              <div style={big}>{val(g.load)}<span style={unit}>%</span></div>
              <div style={sub}>{g.name ?? "No NVIDIA GPU detected"}</div>
              <Spark data={hist.gpu} color="var(--accent)" max={100} />
            </Tile>
            <Tile icon="files" title="VRAM">
              <div style={big}>{g.vram_used_mb === undefined ? "-" : vramGb.toFixed(1)}<span style={unit}>/ {g.vram_total_mb ? Math.round(g.vram_total_mb / 1024) : "-"} GB</span></div>
              <Spark data={hist.vram} color="var(--accent)" max={g.vram_total_mb} />
            </Tile>
            <Tile icon="bolt" title="GPU temp">
              <div style={big}>{val(g.temp)}<span style={unit}>°C</span></div>
              <Spark data={hist.temp} color="#e8b73a" max={100} />
            </Tile>
            <Tile icon="bolt" title="Power">
              <div style={big}>{val(g.power)}<span style={unit}>W</span></div>
              <div style={sub}>{g.power_limit ? `of ${Math.round(g.power_limit)} W limit` : ""}</div>
              <Spark data={hist.power} color="var(--accent)" max={g.power_limit} />
            </Tile>
            <Tile icon="plan" title="PCIe">
              <div style={big}>{g.pcie_gen ? `Gen${g.pcie_gen}` : "-"}<span style={unit}>{g.pcie_width ? `x${g.pcie_width}` : ""}</span></div>
            </Tile>
            <Tile icon="terminal" title="CPU">
              <div style={big}>{val(sys.cpu)}<span style={unit}>%</span></div>
              <div style={sub}>{sys.threads ? `${sys.threads} threads` : ""}</div>
              <Spark data={hist.cpu} color="var(--accent)" max={100} />
            </Tile>
            <Tile icon="files" title="Disk read">
              <div style={big}>{sys.disk_read_mb_s ? sys.disk_read_mb_s.toFixed(0) : "-"}{sys.disk_read_mb_s ? <span style={unit}>MB/s</span> : null}</div>
            </Tile>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "minmax(230px, 1fr) minmax(0, 2.2fr)", gap: 12 }}>
            <div style={{ background: "var(--bg2)", border: "1px solid var(--border)", borderRadius: 14, padding: "16px 18px" }}>
              <div style={{ fontWeight: 700, fontSize: 15 }}>Context fill</div>
              <div style={{ position: "relative", width: 140, height: 90, margin: "10px auto 0" }}>
                <svg viewBox="0 0 140 90" width="140" height="90">
                  <path d="M18 78 A52 52 0 0 1 122 78" fill="none" stroke="var(--surface2)" strokeWidth={9} strokeLinecap="round" />
                  <path d="M18 78 A52 52 0 0 1 122 78" fill="none" stroke="var(--accent)" strokeWidth={9} strokeLinecap="round"
                    strokeDasharray={`${(ctxPct / 100) * C} ${C}`} />
                </svg>
                <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", paddingTop: 18 }}>
                  <div style={{ fontSize: 22, fontWeight: 700 }}>{Math.round(ctxPct)}%</div>
                  <div style={{ fontSize: 10, color: "var(--text-dim)" }}>{snap?.ctx_total ? `${snap.ctx_used} / ${snap.ctx_total}` : "-"}</div>
                </div>
              </div>
              <Bar label="Experts in VRAM" text={snap?.experts ? `${snap.experts.gpu_layers} / ${snap.experts.layers} layers` : "-"}
                pct={snap?.experts ? (snap.experts.gpu_layers / snap.experts.layers) * 100 : 0} color="var(--accent)" />
              <Bar label="System RAM" text={sys.ram_total_gb ? `${val(sys.ram_used_gb, 1)} / ${Math.round(sys.ram_total_gb)} GB` : "-"}
                pct={sys.ram_total_gb ? ((sys.ram_used_gb ?? 0) / sys.ram_total_gb) * 100 : 0} color="#e07a5f" />
              <Bar label="GPU temperature" text={g.temp !== undefined ? `${val(g.temp)} °C` : "-"} pct={g.temp ?? 0} color="#e8b73a" />
            </div>
            <div style={{ background: "var(--bg2)", border: "1px solid var(--border)", borderRadius: 14, padding: "16px 18px", minWidth: 0, overflowX: "auto" }}>
              <div style={{ fontWeight: 700, fontSize: 15, marginBottom: 12 }}>Recent requests</div>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                <thead>
                  <tr style={{ color: "var(--text-dim)", fontSize: 10, textAlign: "left", letterSpacing: "0.05em" }}>
                    {["TIME", "STATUS", "PROMPT", "REUSED", "OUTPUT", "TOK/S", "HIT RATE", "DURATION"].map(h => <th key={h} style={{ padding: "6px 8px", fontWeight: 500 }}>{h}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {(snap?.requests ?? []).length === 0 && <tr><td colSpan={8} style={{ padding: "12px 8px", fontWeight: 600 }}>No requests yet</td></tr>}
                  {(snap?.requests ?? []).map((r, i) => (
                    <tr key={i} style={{ borderTop: "1px solid var(--border)" }}>
                      <td style={{ padding: "7px 8px" }}>{clock(r.time)}</td>
                      <td style={{ padding: "7px 8px", color: r.status === "done" ? "var(--green)" : "var(--text-mid)" }}>{r.status}</td>
                      <td style={{ padding: "7px 8px" }}>{r.prompt}</td>
                      <td style={{ padding: "7px 8px" }}>{r.reused}</td>
                      <td style={{ padding: "7px 8px" }}>{r.output}</td>
                      <td style={{ padding: "7px 8px" }}>{r.tps || "-"}</td>
                      <td style={{ padding: "7px 8px" }}>{Math.round(r.hit_rate * 100)}%</td>
                      <td style={{ padding: "7px 8px" }}>{r.duration}s</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
