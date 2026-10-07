import type { Mode, Agent } from "../types";
import AgentModal from "./AgentModal";
import { useState } from "react";

interface Props {
  mode: Mode;
  onModeChange: (m: Mode) => void;
  connected: boolean;
  tps: number;
  agents: Agent[];
  onRefreshAgents: () => void;
}

const S: Record<string, React.CSSProperties> = {
  root: {
    width: 220, minWidth: 220, height: "100%",
    background: "var(--surface)", borderRight: "1px solid var(--border)",
    display: "flex", flexDirection: "column",
  },
  logo: {
    padding: "18px 16px 14px",
    borderBottom: "1px solid var(--border)",
    display: "flex", alignItems: "center", gap: 8,
  },
  logoIcon: { color: "var(--accent)", fontSize: 16 },
  logoText: { color: "var(--text)", letterSpacing: "0.05em", fontWeight: 600 },
  nav: { flex: 1, padding: "8px 0", overflow: "auto" },
  navItem: {
    padding: "6px 16px", display: "flex", alignItems: "center", gap: 8,
    color: "var(--text-mid)", cursor: "pointer", fontSize: 12,
    userSelect: "none" as const,
  },
  navDot: { width: 6, height: 6, borderRadius: "50%", background: "var(--border2)" },
  section: { padding: "8px 16px 4px", color: "var(--text-dim)", fontSize: 10, letterSpacing: "0.1em" },
  agentRow: {
    padding: "5px 16px", display: "flex", alignItems: "center", gap: 6,
    color: "var(--text-mid)", fontSize: 12, cursor: "default",
  },
  gearBtn: { marginLeft: "auto", color: "var(--text-dim)", fontSize: 11, padding: "0 2px" },
  addBtn: {
    padding: "5px 16px", color: "var(--text-dim)", fontSize: 11,
    cursor: "pointer", display: "flex", alignItems: "center", gap: 6,
  },
  footer: { borderTop: "1px solid var(--border)", padding: "10px 8px" },
  toggle: {
    display: "flex", background: "var(--surface2)",
    borderRadius: 6, border: "1px solid var(--border)", overflow: "hidden",
  },
  toggleBtn: {
    flex: 1, padding: "6px 0", fontSize: 11, textAlign: "center" as const,
    cursor: "pointer", transition: "background 0.15s",
  },
  status: {
    display: "flex", alignItems: "center", gap: 6,
    padding: "6px 8px 0", fontSize: 10, color: "var(--text-dim)",
  },
  dot: { width: 6, height: 6, borderRadius: "50%" },
};

export default function Sidebar({ mode, onModeChange, connected, tps, agents, onRefreshAgents }: Props) {
  const [editingAgent, setEditingAgent] = useState<Agent | null | "new">(null);

  return (
    <aside style={S.root}>
      {/* Logo */}
      <div style={S.logo}>
        <span style={S.logoIcon}>◈</span>
        <span style={S.logoText}>herama</span>
      </div>

      {/* Navigation */}
      <nav style={S.nav}>
        <NavItem label="new conversation" icon="+" />
        <NavItem label="history" icon="○" />
        <NavItem label="files" icon="○" />
        <NavItem label="tasks" icon="○" />
        <NavItem label="settings" icon="○" />

        {/* Agents section in sidebar (visible in agents mode) */}
        {mode === "agents" && (
          <>
            <div style={{ height: 8 }} />
            <div style={S.section}>agents</div>
            {agents.map(a => (
              <div key={a.id} style={S.agentRow}>
                <span style={{ ...S.navDot, background: "var(--accent)" }} />
                <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{a.name}</span>
                <button style={S.gearBtn} onClick={() => setEditingAgent(a)} title="edit">⚙</button>
              </div>
            ))}
            <div style={S.addBtn} onClick={() => setEditingAgent("new")}>
              <span style={{ color: "var(--accent)" }}>+</span>
              <span>new agent</span>
            </div>
          </>
        )}
      </nav>

      {/* Footer: status + mode toggle */}
      <div style={S.footer}>
        <div style={S.status}>
          <span style={{ ...S.dot, background: connected ? "#22c55e" : "var(--border2)" }} />
          <span>{connected ? (tps > 0 ? `${tps.toFixed(1)} t/s` : "online") : "offline"}</span>
        </div>
        <div style={{ height: 8 }} />
        <div style={S.toggle}>
          <ModeBtn label="chat" active={mode === "chat"} onClick={() => onModeChange("chat")} />
          <ModeBtn label="agents" active={mode === "agents"} onClick={() => onModeChange("agents")} />
        </div>
      </div>

      {/* Agent modal */}
      {editingAgent !== null && (
        <AgentModal
          agent={editingAgent === "new" ? undefined : editingAgent}
          onClose={() => setEditingAgent(null)}
          onSaved={() => { setEditingAgent(null); onRefreshAgents(); }}
        />
      )}
    </aside>
  );
}

function NavItem({ label, icon }: { label: string; icon: string }) {
  const [hov, setHov] = useState(false);
  return (
    <div
      style={{ ...S.navItem, background: hov ? "var(--surface2)" : "transparent" }}
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
    >
      <span style={{ color: "var(--text-dim)", width: 12 }}>{icon}</span>
      <span>{label}</span>
    </div>
  );
}

function ModeBtn({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      style={{
        ...S.toggleBtn,
        background: active ? "var(--border2)" : "transparent",
        color: active ? "var(--text)" : "var(--text-dim)",
        fontWeight: active ? 600 : 400,
      }}
      onClick={onClick}
    >
      {label}
    </button>
  );
}
