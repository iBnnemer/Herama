import { useState } from "react";
import type { Agent, Conversation, Mode, Project, View } from "../types";
import AgentModal from "./AgentModal";
import Icon from "./Icons";
import type { IconName } from "./Icons";

interface Props {
  mode: Mode;
  onModeChange: (m: Mode) => void;
  view: View;
  onView: (v: View) => void;
  conversations: Conversation[];
  activeConvId: string;
  onSelectConv: (id: string) => void;
  onNewConv: (projectId?: string) => void;
  onTogglePin: (id: string) => void;
  onDeleteConv: (id: string) => void;
  projects: Project[];
  activeProjectId: string;
  onSelectProject: (p: Project) => void;
  onAddProject: () => void;
  agents: Agent[];
  activeAgentId?: string;
  onOpenAgent: (a: Agent) => void;
  onRefreshAgents: () => void;
  unread: number;
  connected: boolean;
  tps: number;
}

const NAV: { view: View; label: string; icon: IconName }[] = [
  { view: "projects",     label: "Projects",       icon: "files"   },
  { view: "capabilities", label: "Capabilities",   icon: "bolt"    },
  { view: "messaging",    label: "Messaging",      icon: "message" },
  { view: "artifacts",    label: "Artifacts",      icon: "box"     },
  { view: "jobs",         label: "Scheduled jobs", icon: "clock"   },
];

export default function Sidebar(p: Props) {
  const [editAgent, setEditAgent] = useState<Agent | "new" | null>(null);
  const [query, setQuery] = useState("");
  const q = query.trim().toLowerCase();

  const sessions = p.conversations.filter(c => !c.agentId);
  const match = (c: Conversation) =>
    !q || c.title.toLowerCase().includes(q) || c.messages.some(m => m.content.toLowerCase().includes(q));
  const pinned = sessions.filter(c => c.pinned && match(c));
  const recent = sessions.filter(c => !c.pinned && !c.projectId && match(c));
  const projects = p.projects.filter(pr => !q || pr.name.toLowerCase().includes(q)
    || sessions.some(c => c.projectId === pr.id && match(c)));

  const convRow = (c: Conversation) => (
    <ConvRow key={c.id} conv={c} active={p.view === "chat" && c.id === p.activeConvId}
      onClick={() => p.onSelectConv(c.id)} onPin={() => p.onTogglePin(c.id)} onDelete={() => p.onDeleteConv(c.id)} />
  );

  return (
    <aside style={{
      width: 260, minWidth: 260, height: "100%", flexShrink: 0,
      background: "var(--bg2)", borderRight: "1px solid var(--border)",
      display: "flex", flexDirection: "column",
    }}>
      <div className="titlebar" style={{ padding: "14px 16px 10px", display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ color: "var(--accent)", fontSize: 18, lineHeight: 1 }}>◈</span>
        <span style={{ fontWeight: 700, fontSize: 15, letterSpacing: "-0.01em" }}>herama</span>
      </div>

      <div style={{ padding: "0 10px 10px", display: "flex", gap: 4 }}>
        {([["chat", "SESSIONS"], ["agents", "BOTS"]] as [Mode, string][]).map(([m, label]) => (
          <button key={m} onClick={() => p.onModeChange(m)} style={{
            flex: 1, padding: "5px 0", borderRadius: 6, fontSize: 11, letterSpacing: "0.06em",
            background: p.mode === m ? "var(--surface2)" : "transparent",
            color: p.mode === m ? "var(--text)" : "var(--text-dim)",
            fontWeight: p.mode === m ? 600 : 400,
            border: p.mode === m ? "1px solid var(--border2)" : "1px solid transparent",
          }}>{label}</button>
        ))}
      </div>

      {p.mode === "chat" ? (
        <>
          <div style={{ padding: "0 8px 6px" }}>
            <button onClick={() => p.onNewConv()} style={{
              width: "100%", padding: "7px 10px", display: "flex", gap: 8, alignItems: "center",
              background: "var(--surface)", borderRadius: 8, color: "var(--text-mid)", fontSize: 13,
            }}><Icon name="plus" size={14} /> New session</button>
            {NAV.map(n => (
              <button key={n.view} onClick={() => p.onView(n.view)} style={{
                width: "100%", padding: "7px 10px", display: "flex", gap: 10, alignItems: "center", marginTop: 1,
                borderRadius: 8, fontSize: 13, textAlign: "left",
                background: p.view === n.view ? "var(--surface2)" : "transparent",
                color: p.view === n.view ? "var(--text)" : "var(--text-mid)",
              }}>
                <Icon name={n.icon} size={15} />
                <span style={{ flex: 1 }}>{n.label}</span>
                {n.view === "messaging" && p.unread > 0 && (
                  <span style={{ background: "var(--accent)", color: "#000", borderRadius: 9, padding: "0 6px", fontSize: 10, fontWeight: 700 }}>{p.unread}</span>
                )}
              </button>
            ))}
          </div>

          <div style={{ padding: "4px 10px 8px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, padding: "5px 10px", color: "var(--text-dim)" }}>
              <Icon name="search" size={13} />
              <input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search sessions"
                style={{ flex: 1, fontSize: 12, minWidth: 0 }} />
            </div>
          </div>

          <div style={{ flex: 1, overflow: "auto", padding: "0 6px" }}>
            {pinned.length > 0 && <><Label text="Pinned sessions" />{pinned.map(convRow)}</>}

            <Label text="Projects" action={<IconBtn icon="plus" title="add project folder" onClick={p.onAddProject} />} />
            {projects.length === 0 && <Empty text={q ? "no matches" : "no projects yet"} />}
            {projects.map(pr => {
              const open = pr.id === p.activeProjectId || !!q;
              return (
                <div key={pr.id}>
                  <div onClick={() => p.onSelectProject(pr)} style={{
                    display: "flex", alignItems: "center", gap: 8, padding: "6px 10px", borderRadius: 7, cursor: "pointer", fontSize: 13,
                    color: pr.id === p.activeProjectId ? "var(--text)" : "var(--text-mid)",
                  }} title={pr.dir}>
                    <Icon name="files" size={14} />
                    <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{pr.name}</span>
                    <IconBtn icon="plus" title="new session in project" onClick={() => p.onNewConv(pr.id)} />
                  </div>
                  {open && sessions.filter(c => c.projectId === pr.id && match(c)).map(c => <div key={c.id} style={{ paddingLeft: 14 }}>{convRow(c)}</div>)}
                </div>
              );
            })}

            <Label text="Recent" />
            {recent.length === 0 && <Empty text={q ? "no matches" : "no sessions"} />}
            {recent.map(convRow)}
          </div>
        </>
      ) : (
        <div style={{ flex: 1, overflow: "auto", padding: "0 6px" }}>
          <Label text="Bots" action={<IconBtn icon="plus" title="new bot" onClick={() => setEditAgent("new")} />} />
          {p.agents.length === 0 && <Empty text="no bots yet - create one with +" />}
          {p.agents.map(a => (
            <div key={a.id} style={{ display: "flex", alignItems: "center" }}>
              <div onClick={() => p.onOpenAgent(a)} style={{
                flex: 1, padding: "7px 10px", borderRadius: 7, cursor: "pointer", fontSize: 13, display: "flex", alignItems: "center", gap: 8, minWidth: 0,
                background: p.view === "chat" && p.activeAgentId === a.id ? "var(--surface2)" : "transparent",
                color: p.activeAgentId === a.id ? "var(--text)" : "var(--text-mid)",
              }}>
                <span style={{ color: "var(--accent)", fontSize: 8 }}>●</span>
                <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{a.name}</span>
              </div>
              <IconBtn icon="gear" title="edit bot" onClick={() => setEditAgent(a)} />
            </div>
          ))}
        </div>
      )}

      <div style={{ borderTop: "1px solid var(--border)", padding: "10px 14px", display: "flex", alignItems: "center", gap: 8, fontSize: 11, color: "var(--text-dim)" }}>
        <span style={{ width: 6, height: 6, borderRadius: "50%", flexShrink: 0, background: p.connected ? "var(--green)" : "var(--border2)" }} />
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

function Label({ text, action }: { text: string; action?: React.ReactNode }) {
  return (
    <div style={{ display: "flex", alignItems: "center", padding: "10px 8px 3px", fontSize: 10, color: "var(--text-dim)", letterSpacing: "0.08em", textTransform: "uppercase" }}>
      <span style={{ flex: 1 }}>{text}</span>{action}
    </div>
  );
}

function Empty({ text }: { text: string }) {
  return <div style={{ padding: "6px 10px", fontSize: 12, color: "var(--text-dim)" }}>{text}</div>;
}

function IconBtn({ icon, title, onClick }: { icon: IconName; title: string; onClick: () => void }) {
  return (
    <button title={title} onClick={e => { e.stopPropagation(); onClick(); }}
      style={{ padding: 4, color: "var(--text-dim)", display: "flex", borderRadius: 5 }}>
      <Icon name={icon} size={13} />
    </button>
  );
}

function ConvRow({ conv, active, onClick, onPin, onDelete }: { conv: Conversation; active: boolean; onClick: () => void; onPin: () => void; onDelete: () => void }) {
  const [hov, setHov] = useState(false);
  return (
    <div onClick={onClick} onMouseEnter={() => setHov(true)} onMouseLeave={() => setHov(false)} style={{
      padding: "6px 8px 6px 10px", borderRadius: 7, cursor: "pointer", fontSize: 13, display: "flex", alignItems: "center", gap: 4,
      background: active ? "var(--surface2)" : hov ? "var(--surface)" : "transparent",
      color: active ? "var(--text)" : "var(--text-mid)", marginBottom: 1,
    }}>
      <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{conv.title}</span>
      {(hov || conv.pinned) && (
        <button title={conv.pinned ? "unpin" : "pin"} onClick={e => { e.stopPropagation(); onPin(); }}
          style={{ display: "flex", padding: 2, color: conv.pinned ? "var(--accent)" : "var(--text-dim)" }}><Icon name="pin" size={13} /></button>
      )}
      {hov && (
        <button title="delete" onClick={e => { e.stopPropagation(); onDelete(); }}
          style={{ display: "flex", padding: 2, color: "var(--text-dim)" }}><Icon name="trash" size={13} /></button>
      )}
    </div>
  );
}
