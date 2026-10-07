import { useEffect, useRef } from "react";
import type { Message } from "../types";

interface Props { messages: Message[] }

export default function MessageList({ messages }: Props) {
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  if (messages.length === 0) {
    return (
      <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 12, color: "var(--text-dim)" }}>
        <span style={{ fontSize: 32, color: "var(--accent)" }}>◈</span>
        <span style={{ fontSize: 15, color: "var(--text-mid)" }}>how can I help you today?</span>
      </div>
    );
  }

  return (
    <div style={{ flex: 1, overflow: "auto", padding: "24px 0" }}>
      <div style={{ maxWidth: 720, margin: "0 auto", padding: "0 24px" }}>
        {messages.map(m => <MsgRow key={m.id} m={m} />)}
      </div>
      <div ref={endRef} />
    </div>
  );
}

function MsgRow({ m }: { m: Message }) {
  if (m.role === "tool") {
    return (
      <div style={{ margin: "6px 0", display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: "var(--text-dim)" }}>
        <span style={{
          color: m.toolStatus === "done" ? "var(--green)" : m.toolStatus === "error" ? "var(--red)" : "var(--accent)",
          fontSize: 9,
        }}>●</span>
        <span style={{
          padding: "4px 10px", background: "var(--surface)", border: "1px solid var(--border)",
          borderRadius: 6, fontFamily: "var(--mono)", fontSize: 11,
        }}>{m.toolLabel ?? m.content}</span>
      </div>
    );
  }

  const isUser = m.role === "user";
  return (
    <div style={{
      marginBottom: 20,
      display: "flex",
      justifyContent: isUser ? "flex-end" : "flex-start",
    }}>
      {!isUser && (
        <div style={{ width: 28, height: 28, borderRadius: "50%", background: "var(--accent)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, marginRight: 12, fontSize: 12, color: "#000", fontWeight: 700, marginTop: 2 }}>
          ◈
        </div>
      )}
      <div style={{
        maxWidth: isUser ? "72%" : "100%",
        background: isUser ? "var(--surface2)" : "transparent",
        border: isUser ? "1px solid var(--border2)" : "none",
        borderRadius: isUser ? 14 : 0,
        padding: isUser ? "10px 14px" : "2px 0",
        fontSize: 14,
        lineHeight: 1.65,
        color: "var(--text)",
        whiteSpace: "pre-wrap",
        wordBreak: "break-word",
      }}>
        {m.content}
        {m.streaming && <span className="blink" style={{ color: "var(--accent)", marginLeft: 1 }}>▋</span>}
      </div>
      {isUser && (
        <div style={{ width: 28, height: 28, borderRadius: "50%", background: "var(--surface2)", border: "1px solid var(--border2)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, marginLeft: 12, fontSize: 11, color: "var(--text-mid)", marginTop: 2 }}>
          you
        </div>
      )}
    </div>
  );
}
