import { useEffect, useState } from "react";
import type { Model } from "../../types";
import { BASE, fetchSkills, loadTools } from "../../api";
import type { ToolInfo } from "../../api";
import ModelHub from "./ModelHub";
import { approvals, describeKey } from "../../approvals";
import PageShell, { card, ghostBtn, Empty } from "./PageShell";

interface Props {
  models: Model[];
  connected: boolean;
  engine: string;
  runtime: { state: string; backend: string; progress: number; error: string } | null;
  onRetry: () => void;
}

export default function CapabilitiesPage({ models, connected, engine, runtime, onRetry }: Props) {
  const [skills, setSkills] = useState<{ name: string; desc: string }[]>([]);

  const [granted, setGranted] = useState<string[]>(() => approvals.always());
  const [tools, setTools] = useState<ToolInfo[]>([]);
  const [facts, setFacts] = useState<{ id: number; content: string }[]>([]);
  const loadFacts = () => fetch(`${BASE}/api/memory?k=50`).then(r => r.json()).then(d => setFacts(Array.isArray(d) ? d : d.facts ?? [])).catch(() => setFacts([]));
  const dropFact = (id: number) => fetch(`${BASE}/api/memory/${id}`, { method: "DELETE" }).then(loadFacts).catch(() => {});

  useEffect(() => { if (connected) { void fetchSkills().then(setSkills); void loadTools().then(setTools); void loadFacts(); } }, [connected]);

  return (
    <PageShell title="Capabilities" hint="What this local backend can use right now.">
      <h2 style={{ fontSize: 13, color: "var(--text-dim)", margin: "8px 0", textTransform: "uppercase", letterSpacing: "0.08em" }}>Inference engine</h2>
      <div style={{ ...card, display: "flex", alignItems: "center", gap: 12 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontWeight: 600, fontSize: 13 }}>{engine || "unknown"}</div>
          {runtime?.error && <div style={{ fontSize: 12, color: "var(--red)", marginTop: 4, wordBreak: "break-word" }}>{runtime.error}</div>}
          {runtime?.state === "downloading" && <div style={{ fontSize: 12, color: "var(--text-dim)", marginTop: 4 }}>downloading {Math.round(runtime.progress * 100)}%</div>}
        </div>
        {runtime?.state !== "downloading" && <button style={ghostBtn} onClick={onRetry}>Download engine again</button>}
      </div>
      <h2 style={{ fontSize: 13, color: "var(--text-dim)", margin: "20px 0 8px", textTransform: "uppercase", letterSpacing: "0.08em" }}>Models</h2>
      {models.length === 0 && <Empty text="No models found. Put .gguf files in the models folder." />}
      {models.map(m => <div key={m.name} style={card}>{m.name}</div>)}
      <h2 style={{ fontSize: 13, color: "var(--text-dim)", margin: "20px 0 8px", textTransform: "uppercase", letterSpacing: "0.08em" }}>Get models from Hugging Face</h2>
      {connected ? <ModelHub installed={models.map(m => m.name)} /> : <Empty text="Backend offline." />}
      <h2 style={{ fontSize: 13, color: "var(--text-dim)", margin: "20px 0 4px", textTransform: "uppercase", letterSpacing: "0.08em" }}>Agent tools</h2>
      <div style={{ fontSize: 12, color: "var(--text-dim)", marginBottom: 8 }}>Every agent has these, but only the groups your message needs are switched on (for example "search" turns on Web); the model can switch on another group itself. Ask mode confirms file changes and commands, Plan mode allows reading only, Off disables them.</div>
      {["Files", "Web", "Shell", "Skills", "Memory", "Utilities"].map(g => {
        const list = tools.filter(t => t.group === g);
        return list.length === 0 ? null : (
          <div key={g} style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 12, color: "var(--text-mid)", margin: "10px 2px 6px" }}>{g}</div>
            <div style={{ ...card, padding: 0 }}>
              {list.map((t, i) => (
                <div key={t.name} style={{ padding: "12px 16px", borderTop: i ? "1px solid var(--border)" : "none" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontWeight: 700, fontSize: 14 }}>{t.name}</span>
                    <span style={{ fontSize: 10, color: "var(--text-dim)", border: "1px solid var(--border2)", borderRadius: 6, padding: "1px 6px" }}>{t.kind}</span>
                  </div>
                  <div style={{ color: "var(--text-dim)", fontSize: 12, marginTop: 3, lineHeight: 1.5 }}>{t.description}</div>
                </div>
              ))}
            </div>
          </div>
        );
      })}
      {granted.length > 0 && (
        <>
          <div style={{ fontSize: 12, color: "var(--text-mid)", margin: "10px 2px 6px" }}>Always allowed</div>
          {granted.map(k => (
            <div key={k} style={{ ...card, display: "flex", alignItems: "center", gap: 10, fontSize: 13 }}>
              <span style={{ flex: 1, wordBreak: "break-all" }}>{describeKey(k)}</span>
              <button style={ghostBtn} onClick={() => { approvals.forget(k); setGranted(approvals.always()); }}>Remove</button>
            </div>
          ))}
        </>
      )}
      <h2 style={{ fontSize: 13, color: "var(--text-dim)", margin: "20px 0 8px", textTransform: "uppercase", letterSpacing: "0.08em" }}>Memory</h2>
      {facts.length === 0 && <Empty text="No remembered facts yet. Agents save them with the remember tool and they are shared across agents." />}
      {facts.map(f => (
        <div key={f.id} style={{ ...card, display: "flex", alignItems: "center", gap: 10, fontSize: 13 }}>
          <span style={{ flex: 1, wordBreak: "break-word" }}>{f.content}</span>
          <button style={ghostBtn} onClick={() => void dropFact(f.id)}>Delete</button>
        </div>
      ))}
      <h2 style={{ fontSize: 13, color: "var(--text-dim)", margin: "20px 0 8px", textTransform: "uppercase", letterSpacing: "0.08em" }}>Skills</h2>
      {skills.length === 0 && <Empty text="No skills yet. Skills are generated by the backend and saved in the skills folder." />}
      {skills.map(s => (
        <div key={s.name} style={card}>
          <div style={{ fontWeight: 600, fontSize: 13 }}>{s.name}</div>
          {s.desc && <div style={{ color: "var(--text-dim)", fontSize: 12, marginTop: 2 }}>{s.desc}</div>}
        </div>
      ))}
    </PageShell>
  );
}
