import { useState } from "react";
import type { Job } from "../../types";
import { rid } from "../../util";
import PageShell, { card, ghostBtn, primaryBtn, Empty } from "./PageShell";

interface Props {
  jobs: Job[];
  onChange: (jobs: Job[]) => void;
  onRunNow: (id: string) => void;
}

const EVERY = [[5, "every 5 minutes"], [15, "every 15 minutes"], [30, "every 30 minutes"], [60, "every hour"], [360, "every 6 hours"], [1440, "every day"]] as const;

const field: React.CSSProperties = {
  width: "100%", background: "var(--bg2)", border: "1px solid var(--border)", borderRadius: 8, padding: "7px 10px", fontSize: 13, marginBottom: 8,
};

export default function JobsPage({ jobs, onChange, onRunNow }: Props) {
  const [name, setName] = useState("");
  const [prompt, setPrompt] = useState("");
  const [every, setEvery] = useState<number>(60);

  const add = () => {
    if (!name.trim() || !prompt.trim()) return;
    onChange([...jobs, { id: rid(), name: name.trim(), prompt: prompt.trim(), everyMin: every, enabled: true, createdAt: Date.now() }]);
    setName(""); setPrompt("");
  };

  return (
    <PageShell title="Scheduled jobs" hint="Prompts that run automatically while the app is open. Results arrive in Messaging.">
      <div style={card}>
        <input style={field} placeholder="Job name" value={name} onChange={e => setName(e.target.value)} />
        <textarea style={{ ...field, minHeight: 70 }} placeholder="Prompt to run" value={prompt} onChange={e => setPrompt(e.target.value)} />
        <div style={{ display: "flex", gap: 8 }}>
          <select value={every} onChange={e => setEvery(+e.target.value)} style={{ ...field, width: "auto", marginBottom: 0 }}>
            {EVERY.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          <button style={primaryBtn} onClick={add}>Add job</button>
        </div>
      </div>
      {jobs.length === 0 && <Empty text="No scheduled jobs." />}
      {jobs.map(j => (
        <div key={j.id} style={{ ...card, display: "flex", alignItems: "center", gap: 10, opacity: j.enabled ? 1 : 0.55 }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontWeight: 600, fontSize: 13 }}>{j.name}</div>
            <div style={{ fontSize: 12, color: "var(--text-dim)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{j.prompt}</div>
            <div style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 2 }}>
              {EVERY.find(e => e[0] === j.everyMin)?.[1] ?? `every ${j.everyMin} min`}
              {j.lastRun ? ` - last run ${new Date(j.lastRun).toLocaleString()}` : " - never run"}
            </div>
          </div>
          <button style={ghostBtn} onClick={() => onRunNow(j.id)}>Run now</button>
          <button style={ghostBtn} onClick={() => onChange(jobs.map(x => x.id === j.id ? { ...x, enabled: !x.enabled } : x))}>{j.enabled ? "Pause" : "Resume"}</button>
          <button style={{ ...ghostBtn, color: "var(--red)" }} onClick={() => onChange(jobs.filter(x => x.id !== j.id))}>Delete</button>
        </div>
      ))}
    </PageShell>
  );
}
