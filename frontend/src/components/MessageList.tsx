import { useEffect, useRef } from "react";
import type { Message } from "../types";

interface Props { messages: Message[] }

const S: Record<string, React.CSSProperties> = {
  list: { flex: 1, overflow: "auto", padding: "16px 0" },
  msg: { padding: "8px 24px", display: "flex", flexDirection: "column", gap: 2 },
  header: { display: "flex", alignItems: "center", gap: 8, marginBottom: 4 },
  role: { fontSize: 11, fontWeight: 600 },
  ts: { fontSize: 10, color: "var(--text-dim)" },
  body: { fontSize: 13, lineHeight: 1.6, whiteSpace: "pre-wrap", wordBreak: "break-word" },
  tool: {
    margin: "4px 0", padding: "6px 10px",
    border: "1px solid var(--border)", borderRadius: 4,
    background: "var(--surface2)", fontSize: 11,
    display: "flex", alignItems: "center", gap: 6,
  },
};

export default function MessageList({ messages }: Props) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <div style={S.list}>
      {messages.map(m => (
        m.role === "tool" ? (
          <div key={m.id} style={{ padding: "2px 24px" }}>
            <div style={S.tool}>
              <span>{m.toolStatus === "done" ? "●" : m.toolStatus === "error" ? "✕" : "○"}</span>
              <span style={{ color: m.toolStatus === "error" ? "#ef4444" : m.toolStatus === "done" ? "var(--text-mid)" : "var(--accent)" }}>
                {m.toolLabel ?? m.content}
              </span>
            </div>
          </div>
        ) : (
          <div key={m.id} style={S.msg}>
            <div style={S.header}>
              <span style={{ ...S.role, color: m.role === "user" ? "var(--accent)" : "var(--text)" }}>
                {m.role === "user" ? "▶  you" : "◈  herama"}
              </span>
              <span style={S.ts}>{new Date(m.ts).toLocaleTimeString()}</span>
            </div>
            <div style={S.body}>
              {m.content}
              {m.streaming && <span className="blink" style={{ color: "var(--text-dim)" }}>▋</span>}
            </div>
          </div>
        )
      ))}
      <div ref={endRef} />
    </div>
  );
}
