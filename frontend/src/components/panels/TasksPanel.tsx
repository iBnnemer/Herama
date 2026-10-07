import type { Task } from "../../types";

interface Props { tasks: Task[]; onClear: () => void }

const COLOR = { running: "var(--accent)", done: "var(--green)", error: "var(--red)" } as const;

export default function TasksPanel({ tasks, onClear }: Props) {
  const finished = tasks.some(t => t.status !== "running");
  return (
    <div style={{ flex: 1, overflow: "auto", padding: 8 }}>
      {tasks.length === 0 && <div style={{ color: "var(--text-dim)", fontSize: 12, padding: 8 }}>no background tasks yet</div>}
      {tasks.map(t => (
        <div key={t.id} style={{ display: "flex", gap: 8, alignItems: "center", padding: "6px 8px", fontSize: 12, borderRadius: 6 }}>
          <span className={t.status === "running" ? "blink" : undefined} style={{ color: COLOR[t.status], fontSize: 9 }}>●</span>
          <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={t.label}>{t.label}</span>
          <span style={{ color: "var(--text-dim)", fontSize: 10 }}>{new Date(t.ts).toLocaleTimeString()}</span>
        </div>
      ))}
      {finished && (
        <button onClick={onClear} style={{ margin: "6px 8px", fontSize: 11, color: "var(--text-dim)" }}>clear finished</button>
      )}
    </div>
  );
}
