import { useMemo } from "react";
import type { Conversation } from "../../types";
import PageShell, { card, ghostBtn, Empty } from "./PageShell";

interface Artifact { key: string; session: string; lang: string; code: string; ts: number }

const FENCE = /```([\w+-]*)\n([\s\S]*?)```/g;

export default function ArtifactsPage({ conversations }: { conversations: Conversation[] }) {
  const items = useMemo(() => {
    const out: Artifact[] = [];
    for (const c of conversations) {
      for (const m of c.messages) {
        if (m.role !== "assistant" || m.streaming) continue;
        let i = 0;
        for (const hit of m.content.matchAll(FENCE)) {
          out.push({ key: `${m.id}-${i++}`, session: c.title, lang: hit[1] || "text", code: hit[2], ts: m.ts });
        }
      }
    }
    return out.sort((a, b) => b.ts - a.ts);
  }, [conversations]);

  return (
    <PageShell title="Artifacts" hint="Code blocks produced in your sessions.">
      {items.length === 0 && <Empty text="No code blocks yet." />}
      {items.map(a => (
        <div key={a.key} style={card}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8, fontSize: 11, color: "var(--text-dim)" }}>
            <span style={{ flex: 1 }}>{a.lang} - {a.session}</span>
            <button style={ghostBtn} onClick={() => { void navigator.clipboard?.writeText(a.code); }}>Copy</button>
          </div>
          <pre style={{ margin: 0, fontSize: 12, overflow: "auto", maxHeight: 280, color: "var(--text-mid)" }}>{a.code}</pre>
        </div>
      ))}
    </PageShell>
  );
}
