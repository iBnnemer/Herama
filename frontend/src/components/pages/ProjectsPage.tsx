import { useState } from "react";
import type { Agent, Conversation, Project } from "../../types";
import { projectFolders } from "../../util";
import Modal from "../Modal";
import PageShell, { card, ghostBtn, primaryBtn, Empty } from "./PageShell";

interface Props {
  projects: Project[];
  conversations: Conversation[];
  agents: Agent[];
  activeProjectId: string;
  openId: string;
  onOpenId: (id: string) => void;
  creating: boolean;
  onCloseCreate: () => void;
  onCreate: (name: string, brief: string, folders: string[]) => void;
  onStartCreate: () => void;
  onUpdate: (id: string, patch: Partial<Project>) => void;
  onOpenConv: (id: string) => void;
  onNewSession: (projectId: string) => void;
  onRemove: (id: string) => void;
}

const input: React.CSSProperties = {
  width: "100%", background: "var(--bg2)", border: "1px solid var(--border)", borderRadius: 8,
  padding: "8px 12px", color: "var(--text)", fontSize: 13,
};
const label: React.CSSProperties = { fontSize: 12, color: "var(--text-dim)", margin: "16px 0 6px", textTransform: "uppercase", letterSpacing: "0.08em" };

function NewProject(p: { onClose: () => void; onCreate: (name: string, brief: string, folders: string[]) => void }) {
  const [name, setName] = useState("");
  const [brief, setBrief] = useState("");
  const [folders, setFolders] = useState<string[]>([]);
  const add = async () => {
    const d = await window.herama?.pickFolder();
    if (d && !folders.includes(d)) setFolders([...folders, d]);
  };
  return (
    <Modal title="New project" onClose={p.onClose}>
      <div style={{ ...label, marginTop: 0 }}>Name</div>
      <input style={input} autoFocus value={name} onChange={e => setName(e.target.value)} />
      <div style={label}>What is this project about?</div>
      <textarea style={{ ...input, minHeight: 90, resize: "vertical" }} value={brief} onChange={e => setBrief(e.target.value)}
        placeholder="Describe it in a few words. The model writes the description and instructions for you." />
      <div style={{ display: "flex", alignItems: "center", ...label }}>
        <span style={{ flex: 1 }}>Folders</span>
        <button style={ghostBtn} onClick={() => void add()}>Add folder</button>
      </div>
      {folders.map(f => (
        <div key={f} style={{ ...card, display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ flex: 1, fontSize: 12, wordBreak: "break-all" }}>{f}</span>
          <button style={{ ...ghostBtn, color: "var(--red)" }} onClick={() => setFolders(folders.filter(x => x !== f))}>Remove</button>
        </div>
      ))}
      <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 18 }}>
        <button style={primaryBtn} disabled={!name.trim()} onClick={() => p.onCreate(name.trim(), brief.trim(), folders)}>Create</button>
      </div>
    </Modal>
  );
}

export default function ProjectsPage(p: Props) {
  const open = p.projects.find(x => x.id === p.openId);
  if (open) return <ProjectDetail {...p} project={open} />;

  return (
    <PageShell title="Projects" hint="A project holds instructions, knowledge folders and a managing agent that every session in it uses."
      action={<button style={primaryBtn} onClick={p.onStartCreate}>New project</button>}>
      {p.creating && <NewProject onClose={p.onCloseCreate} onCreate={p.onCreate} />}
      {p.projects.length === 0 && <Empty text="No projects yet. Create one to get started." />}
      {p.projects.map(pr => {
        const n = p.conversations.filter(c => c.projectId === pr.id).length;
        const agent = p.agents.find(a => a.id === pr.agentId);
        return (
          <div key={pr.id} onClick={() => p.onOpenId(pr.id)}
            style={{ ...card, cursor: "pointer", borderColor: pr.id === p.activeProjectId ? "var(--accent)" : "var(--border)" }}>
            <div style={{ fontSize: 14, fontWeight: 600 }}>{pr.name}</div>
            {pr.description && <div style={{ fontSize: 12, color: "var(--text-mid)", marginTop: 2 }}>{pr.description}</div>}
            <div style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 6 }}>
              {projectFolders(pr).length} folder{projectFolders(pr).length === 1 ? "" : "s"} - {n} session{n === 1 ? "" : "s"}
              {agent ? ` - managed by ${agent.name}` : ""}
            </div>
          </div>
        );
      })}
    </PageShell>
  );
}

function ProjectDetail(p: Props & { project: Project }) {
  const pr = p.project;
  const sessions = p.conversations.filter(c => c.projectId === pr.id);
  const folders = projectFolders(pr);
  const setFolders = (list: string[]) => p.onUpdate(pr.id, { folders: list, dir: undefined });
  const addFolder = async () => {
    const d = await window.herama?.pickFolder();
    if (d && !folders.includes(d)) setFolders([...folders, d]);
  };

  return (
    <PageShell title={pr.name} hint="Everything here is added to the context of every session in this project."
      action={<button style={ghostBtn} onClick={() => p.onOpenId("")}>All projects</button>}>
      <div style={label}>Name</div>
      <input style={input} value={pr.name} onChange={e => p.onUpdate(pr.id, { name: e.target.value })} />
      <div style={label}>Description</div>
      <input style={input} value={pr.description ?? ""} placeholder="What is this project about?"
        onChange={e => p.onUpdate(pr.id, { description: e.target.value })} />

      <div style={label}>Instructions</div>
      <textarea style={{ ...input, minHeight: 110, resize: "vertical" }} value={pr.instructions ?? ""}
        placeholder="How should the model behave in this project? Tone, rules, background..."
        onChange={e => p.onUpdate(pr.id, { instructions: e.target.value })} />

      <div style={label}>Project agent</div>
      <select style={input} value={pr.agentId ?? ""} onChange={e => p.onUpdate(pr.id, { agentId: e.target.value || undefined })}>
        <option value="">No agent (default model)</option>
        {p.agents.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
      </select>
      <div style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 4 }}>The agent manages the project: its prompt and model are used by new sessions here.</div>

      <div style={{ display: "flex", alignItems: "center", ...label }}>
        <span style={{ flex: 1 }}>Folders</span>
        <button style={ghostBtn} onClick={() => void addFolder()}>Add folder</button>
      </div>
      {folders.length === 0 && <Empty text="No folders. Add folders the model should know about." />}
      {folders.map(f => (
        <div key={f} style={{ ...card, display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ flex: 1, fontSize: 12, wordBreak: "break-all" }}>{f}</span>
          <button style={{ ...ghostBtn, color: "var(--red)" }} onClick={() => setFolders(folders.filter(x => x !== f))}>Remove</button>
        </div>
      ))}
      <div style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 4 }}>The file tree and text files of these folders are added to every session. The first folder is used by the file browser and terminal.</div>

      <div style={{ display: "flex", alignItems: "center", ...label }}>
        <span style={{ flex: 1 }}>Sessions</span>
        <button style={primaryBtn} onClick={() => p.onNewSession(pr.id)}>New session</button>
      </div>
      {sessions.length === 0 && <Empty text="No sessions yet." />}
      {sessions.map(c => (
        <div key={c.id} style={{ ...card, cursor: "pointer", fontSize: 13 }} onClick={() => p.onOpenConv(c.id)}>{c.title}</div>
      ))}

      <div style={{ marginTop: 28 }}>
        <button style={{ ...ghostBtn, color: "var(--red)" }}
          onClick={() => { if (confirm(`Delete project "${pr.name}"? Its sessions are kept.`)) { p.onRemove(pr.id); p.onOpenId(""); } }}>
          Delete project
        </button>
      </div>
    </PageShell>
  );
}
