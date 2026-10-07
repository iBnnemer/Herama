import { useState } from "react";
import type { Mode, Conversation, Agent } from "../types";
import AgentModal from "./AgentModal";

interface Props {
  mode: Mode;
  onModeChange: (m: Mode) => void;
  conversations: Conversation[];
  agentConvs: Conversation[];
  activeConvId: string;
  onSelectConv: (id: string) => void;
  onNewConv: () => void;
  agents: Agent[];
  connected: boolean;
  tps: number;
  onRefreshAgents: () => void;
}

export default function Sidebar(p: Props) {
  const [editAgent, setEditAgent] = useState<Agent | "new" | null>(null);

  return (
    <aside style={{
      width: 260, minWidth: 260, height: "100%", flexShrink: 0,
      background: "var(--bg2)", borderRight: "1px solid var(--border)",
      display: "flex", flexDirection: "column",
    }}>
      {/* Title bar / logo */}
      <div className="titlebar" style={{
        padding: "14px 16px 10px",
        display: "flex", alignItems: "center", gap: 8,
      }}>
        <span style={{ color: "var(--accent)", fontSize: 18, lineHeight: 1 }}>◈</span>
        <span style={{ fontWeight: 700, fontSize: 15, letterSpacing: "-0.01em" }}>herama</span>
        <div style={{
          marginLeft: "auto", width: 7, height: 7, borderRadius: "50%",
          background: p.connected ? "var(--green)" : "var(--border2)",
          flexShrink: 0,
        }} title={p.connected ? (p.tps > 0 ? `${p.tps.toFixed(1)} t/s` : "online") : "offline"} />
      </div>

      {/* New chat button */}
      <div style={{ padding: "0 10px 8px" }}>
        <button
          onClick={p.onNewConv}
          style={{
            width: "100%", padding: "8px 12px", textAlign: "left",
            background: "var(--surface)", borderRadius: "var(--r)",
            color: "var(--text-mid)", fontSize: 13, display: "flex", gap: 8, alignItems: "center",
          }}
        >
          <span style={{ fontSize: 16, lineHeight: 1, color: "var(--text-dim)" }}>+</span>
          <span>new conversation</span>
        </button>
      </div>

      {/* Mode toggle */}
      <div style={{ padding: "0 10px 10px", display: "flex", gap: 4 }}>
        {(["chat", "agents"] as Mode[]).map(m => (
          <button
            key={m}
            onClick={() => p.onModeChange(m)}
            style={{
              flex: 1, padding: "5px 0", borderRadius: 6, fontSize: 12,
              background: p.mode === m ? "var(--surface2)" : "transparent",
              color: p.mode === m ? "var(--text)" : "var(--text-dim)",
              fontWeight: p.mode === m ? 600 : 400,
              border: p.mode === m ? "1px solid var(--border2)" : "1px solid transparent",
            }}
          >{m}</button>
        ))}
      </div>

      {/* List */}
      <div style={{ flex: 1, overflow: "auto", padding: "0 6px" }}>
        {p.mode === "chat" ? (
          <>
            <SectionLabel label="conversations" />
            {p.conversations.length === 0 && <Empty text="no conversations yet" />}
            {p.conversations.map(c => (
              <ConvRow key={c.id} title={c.title} active={c.id === p.activeConvId} onClick={() => p.onSelectConv(c.id)} />
            ))}
          </>
        ) : (
          <>
            <SectionLabel label="agents" />
            {p.agents.length === 0 && <Empty text="no agents" />}
            {p.agents.map(a => (
              <div key={a.id} style={{ display: "flex", alignItems: "center" }}>
                <ConvRow title={a.name} active={false} onClick={() => {}} dot={<span style={{ color: "var(--accent)", fontSize: 8 }}>●</span>} />
                <button onClick={() => setEditAgent(a)} style={{ padding: "0 8px", color: "var(--text-dim)", fontSize: 12, flexShrink: 0 }}>⚙</button>
              </div>
            ))}
            <button
              onClick={() => setEditAgent("new")}
              style={{ padding: "7px 10px", color: "var(--text-dim)", fontSize: 12, display: "flex", gap: 6, alignItems: "center", width: "100%" }}
            >
              <span style={{ color: "var(--accent)" }}>+</span> new agent
            </button>
          </>
        )}
      </div>

      {/* Bottom status */}
      <div style={{
        borderTop: "1px solid var(--border)", padding: "10px 14px",
        display: "flex", alignItems: "center", gap: 8, fontSize: 11, color: "var(--text-dim)",
      }}>
        <span style={{
          width: 6, height: 6, borderRadius: "50%", flexShrink: 0,
          background: p.connected ? "var(--green)" : "var(--border2)",
        }} />
        <span>{p.connected ? (p.tps > 0 ? `${p.tps.toFixed(1)} t/s` : "backend online") : "backend offline"}</span>
      </div>

      {editAgent !== null && (
        <AgentModal
          agent={editAgent === "new" ? undefined : editAgent}
          onClose={() => setEditAgent(null)}
          onSaved={() => { setEditAgent(null); p.onRefreshAgents(); }}
        />
      )}
    </aside>
  );
}

function SectionLabel({ label }: { label: string }) {
  return <div style={{ padding: "6px 8px 3px", fontSize: 10, color: "var(--text-dim)", letterSpacing: "0.08em", textTransform: "uppercase" as const }}>{label}</div>;
}

function Empty({ text }: { text: string }) {
  return <div style={{ padding: "8px 10px", fontSize: 12, color: "var(--text-dim)" }}>{text}</div>;
}

function ConvRow({ title, active, onClick, dot }: { title: string; active: boolean; onClick: () => void; dot?: React.ReactNode }) {
  const [hov, setHov] = useState(false);
  return (
    <div
      onClick={onClick}
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      style={{
        flex: 1, padding: "7px 10px", borderRadius: 7, cursor: "pointer", fontSize: 13,
        background: active ? "var(--surface2)" : hov ? "var(--surface)" : "transparent",
        color: active ? "var(--text)" : "var(--text-mid)",
        display: "flex", alignItems: "center", gap: 7,
        overflow: "hidden", marginBottom: 1,
      }}
    >
      {dot}
      <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{title}</span>
    </div>
  );
}
