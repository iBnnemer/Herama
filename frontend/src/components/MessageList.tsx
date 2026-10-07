import Markdown from "./Markdown";
import { useEffect, useRef } from "react";
import type { Message } from "../types";
import { splitThink } from "../util";

export default function MessageList({ messages, footer }: { messages: Message[]; footer?: React.ReactNode }) {
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, footer]);

  if (messages.length === 0) {
    return (
      <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 12 }}>
        <span style={{ fontSize: 32, color: "var(--accent)" }}>◈</span>
        <span style={{ fontSize: 17, color: "var(--text-mid)" }}>How can I help you today?</span>
      </div>
    );
  }

  return (
    <div style={{ flex: 1, overflow: "auto", padding: "24px 0" }}>
      <div style={{ maxWidth: 720, margin: "0 auto", padding: "0 24px" }}>
        {messages.map(m => <MsgRow key={m.id} m={m} />)}
        {footer}
      </div>
      <div ref={endRef} />
    </div>
  );
}

function MsgRow({ m }: { m: Message }) {
  if (m.role === "tool") {
    const mark = m.toolStatus === "running" ? "…" : m.toolStatus === "error" ? "✗" : "✓";
    const color = m.toolStatus === "error" ? "var(--red)" : "var(--text-dim)";
    return (
      <details style={{ margin: "6px 0", fontSize: 12, color: "var(--text-dim)", fontFamily: "var(--mono)" }}>
        <summary style={{ cursor: m.content ? "pointer" : "default", userSelect: "none" }}>
          <span style={{ color, marginInlineEnd: 6 }}>{mark}</span>{m.toolLabel ?? "tool"}
        </summary>
        {m.content && <pre style={{ margin: "6px 0 0", padding: "8px 10px", background: "var(--bg2)", borderRadius: 8, whiteSpace: "pre-wrap", wordBreak: "break-word", maxHeight: 240, overflow: "auto", color: "var(--text-mid)" }}>{m.content.slice(0, 4000)}</pre>}
      </details>
    );
  }

  const isUser = m.role === "user";
  const parts = isUser ? null : splitThink(m.content);
  const answer = parts ? parts.answer : (m.display ?? m.content);
  const waiting = m.streaming && !m.content;

  return (
    <div style={{ marginBottom: 22 }}>
      <div dir="auto" style={{
        width: isUser ? "fit-content" : "auto",
        maxWidth: "100%",
        background: isUser ? "var(--surface)" : "transparent",
        border: isUser ? "1px solid var(--border)" : "none",
        borderRadius: isUser ? 14 : 0,
        padding: isUser ? "10px 16px" : 0,
        fontSize: 15,
        lineHeight: 1.7,
        color: "var(--text)",
        whiteSpace: "pre-wrap",
        wordBreak: "break-word",
        unicodeBidi: "plaintext",
        textAlign: "start",
      }}>
        {isUser && (m.images?.length || m.files?.length) ? (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: m.display ? 8 : 0 }}>
            {m.images?.map((src, i) => <img key={i} src={src} alt="" style={{ maxHeight: 160, maxWidth: "100%", borderRadius: 10 }} />)}
            {m.files?.map(f => <span key={f} style={{ fontSize: 12, background: "var(--bg2)", border: "1px solid var(--border)", borderRadius: 8, padding: "3px 8px", color: "var(--text-mid)" }}>{f}</span>)}
          </div>
        ) : null}
        {parts?.think ? (
          <details style={{ marginBottom: 10, fontSize: 13, color: "var(--text-dim)" }}>
            <summary style={{ cursor: "pointer", userSelect: "none" }}>{parts.open ? "Thinking..." : "Thought process"}</summary>
            <div dir="auto" style={{ marginTop: 6, paddingInlineStart: 12, borderInlineStart: "2px solid var(--border)", whiteSpace: "pre-wrap" }}>{parts.think}</div>
          </details>
        ) : null}
        {waiting ? <span className="blink" style={{ color: "var(--accent)" }}>●</span> : isUser ? answer : <Markdown text={answer} />}
        {m.streaming && !waiting && <span className="blink" style={{ color: "var(--accent)", marginInlineStart: 2 }}>▋</span>}
      </div>
    </div>
  );
}
