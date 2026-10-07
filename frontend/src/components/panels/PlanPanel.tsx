import { useEffect, useState } from "react";

interface Item { id: string; text: string; done: boolean; doing?: boolean }

const KEY = "herama.plan";

function load(): Item[] {
  try { return JSON.parse(localStorage.getItem(KEY) || "[]"); } catch { return []; }
}

export default function PlanPanel() {
  const [items, setItems] = useState<Item[]>(load);
  const [text, setText] = useState("");

  useEffect(() => {
    const reload = () => setItems(load());
    window.addEventListener("herama:plan", reload);
    return () => window.removeEventListener("herama:plan", reload);
  }, []);

  useEffect(() => {
    try { localStorage.setItem(KEY, JSON.stringify(items)); } catch { /* storage unavailable */ }
  }, [items]);

  const add = () => {
    const t = text.trim();
    if (!t) return;
    setItems(p => [...p, { id: String(Date.now()), text: t, done: false }]);
    setText("");
  };

  const done = items.filter(i => i.done).length;

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0 }}>
      <div style={{ padding: "6px 12px", fontSize: 11, color: "var(--text-dim)" }}>{done}/{items.length} done</div>
      <div style={{ flex: 1, overflow: "auto", padding: "0 8px" }}>
        {items.map(i => (
          <div key={i.id} style={{ display: "flex", alignItems: "center", gap: 8, padding: "5px 4px", fontSize: 13 }}>
            <input type="checkbox" checked={i.done} style={{ accentColor: "var(--accent)" }}
              onChange={() => setItems(p => p.map(x => x.id === i.id ? { ...x, done: !x.done } : x))} />
            <span style={{ flex: 1, textDecoration: i.done ? "line-through" : "none", color: i.done ? "var(--text-dim)" : i.doing ? "var(--accent)" : "var(--text)" }}>{i.text}</span>
            <button onClick={() => setItems(p => p.filter(x => x.id !== i.id))} style={{ color: "var(--text-dim)" }}>×</button>
          </div>
        ))}
      </div>
      <div style={{ padding: 8, borderTop: "1px solid var(--border)" }}>
        <input value={text} onChange={e => setText(e.target.value)} onKeyDown={e => { if (e.key === "Enter") add(); }}
          placeholder="add a step..." style={{ width: "100%", background: "var(--bg2)", border: "1px solid var(--border)", borderRadius: 6, padding: "6px 10px", fontSize: 12 }} />
      </div>
    </div>
  );
}
