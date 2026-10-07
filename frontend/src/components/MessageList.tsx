import Markdown from "./Markdown";
import { useEffect, useRef, useState } from "react";
import Icon from "./Icons";
import type { Message } from "../types";
import { splitThink } from "../util";

interface Actions {
  onReply: (text: string) => void;
  onEdit: (id: string, text: string) => void;
  onReact: (id: string, emoji: string | undefined) => void;
  canEdit: boolean;
}

const REACTIONS = ["\u{1F44D}", "\u{1F44E}", "\u2764\uFE0F", "\u{1F602}", "\u{1F389}", "\u{1F914}"];

export default function MessageList({ messages, footer, actions }: { messages: Message[]; footer?: React.ReactNode; actions: Actions }) {
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
        {messages.map(m => <MsgRow key={m.id} m={m} actions={actions} />)}
        {footer}
      </div>
      <div ref={endRef} />
    </div>
  );
}

function MsgRow({ m, actions }: { m: Message; actions: Actions }) {
  const [editing, setEditing] = useState<string | null>(null);
  const [picking, setPicking] = useState(false);
  const [copied, setCopied] = useState(false);
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

  const plain = isUser ? (m.display ?? m.content) : answer;
  const copy = () => { void navigator.clipboard?.writeText(plain).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1200); }).catch(() => {}); };
  const quote = plain.split("\n").map(l => `> ${l}`).join("\n") + "\n\n";
  const time = new Date(m.ts).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  const editable = isUser && actions.canEdit && !m.images?.length && !m.files?.length;

  if (editing !== null) {
    return (
      <div style={{ marginBottom: 22 }}>
        <textarea dir="auto" value={editing} onChange={e => setEditing(e.target.value)} autoFocus rows={Math.min(10, Math.max(3, editing.split("\n").length))}
          style={{ width: "100%", background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 12, padding: "10px 14px", color: "var(--text)", fontSize: 15, lineHeight: 1.6, resize: "vertical" }} />
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 8 }}>
          <button onClick={() => setEditing(null)} style={{ padding: "6px 14px", border: "1px solid var(--border)", borderRadius: 8, color: "var(--text-mid)", fontSize: 13 }}>cancel</button>
          <button onClick={() => { const t = editing.trim(); setEditing(null); if (t) actions.onEdit(m.id, t); }}
            style={{ padding: "6px 14px", background: "var(--accent)", color: "#000", borderRadius: 8, fontWeight: 600, fontSize: 13 }}>send</button>
        </div>
      </div>
    );
  }

  return (
    <div className="msg-row" style={{ marginBottom: 22 }}>
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
      {!m.streaming && (m.content || m.display) && (
        <div className="msg-actions" style={{ display: "flex", alignItems: "center", gap: 2, marginTop: 6, position: "relative", color: "var(--text-dim)", fontSize: 12 }}>
          {m.reaction && <span style={{ marginInlineEnd: 6, fontSize: 14 }}>{m.reaction}</span>}
          <span style={{ marginInlineEnd: 6 }}>{time}</span>
          <button className="msg-btn" title={copied ? "copied" : "copy"} onClick={copy}><Icon name={copied ? "check" : "copy"} size={14} /></button>
          <button className="msg-btn" title="reply (quote in the message box)" onClick={() => actions.onReply(quote)}><Icon name="reply" size={14} /></button>
          {editable && <button className="msg-btn" title="edit and resend" onClick={() => setEditing(plain)}><Icon name="edit" size={14} /></button>}
          <button className="msg-btn" title="react" onClick={() => setPicking(p => !p)}><Icon name="smile" size={14} /></button>
          {picking && (
            <div style={{ position: "absolute", bottom: 32, insetInlineStart: 0, display: "flex", gap: 2, padding: 4, background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 10, zIndex: 5 }}>
              {REACTIONS.map(e => (
                <button key={e} className="msg-btn" style={{ fontSize: 16, width: 30 }}
                  onClick={() => { actions.onReact(m.id, m.reaction === e ? undefined : e); setPicking(false); }}>{e}</button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
