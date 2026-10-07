import type { InboxItem } from "../../types";
import PageShell, { card, ghostBtn, Empty } from "./PageShell";

interface Props { items: InboxItem[]; onDelete: (id: string) => void; onClear: () => void }

export default function MessagingPage({ items, onDelete, onClear }: Props) {
  return (
    <PageShell title="Messaging" hint="Results delivered by scheduled jobs while you were away."
      action={items.length > 0 ? <button style={ghostBtn} onClick={onClear}>Clear all</button> : undefined}>
      {items.length === 0 && <Empty text="Inbox is empty." />}
      {items.map(m => (
        <div key={m.id} style={card}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
            <span style={{ fontWeight: 600, fontSize: 13, flex: 1 }}>{m.title}</span>
            <span style={{ fontSize: 11, color: "var(--text-dim)" }}>{new Date(m.ts).toLocaleString()}</span>
            <button onClick={() => onDelete(m.id)} style={{ color: "var(--text-dim)" }}>×</button>
          </div>
          <div style={{ fontSize: 13, whiteSpace: "pre-wrap", wordBreak: "break-word", color: "var(--text-mid)" }}>{m.text}</div>
        </div>
      ))}
    </PageShell>
  );
}
