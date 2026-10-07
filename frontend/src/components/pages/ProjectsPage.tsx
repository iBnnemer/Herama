import { useRef, useState } from "react";
import type { Agent, Conversation, Project } from "../../types";
import { readProjectFile } from "../../util";
import PageShell, { card, ghostBtn, primaryBtn, Empty } from "./PageShell";

interface Props {
  projects: Project[];
  conversations: Conversation[];
  agents: Agent[];
  activeProjectId: string;
  openId: string;
  onOpenId: (id: string) => void;
  onCreate: () => void;
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
const kb = (n: number) => (n >= 1024 ? `${Math.round(n / 1024)} KB` : `${n} B`);

export default function ProjectsPage(p: Props) {
  const open = p.projects.find(x => x.id === p.openId);
  if (open) return <ProjectDetail {...p} project={open} />;

  return (
    <PageShell title="Projects" hint="A project holds instructions, knowledge files and a managing agent that every session in it uses."
      action={<button style={primaryBtn} onClick={p.onCreate}>New project</button>}>
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
              {(pr.files ?? []).length} file{(pr.files ?? []).length === 1 ? "" : "s"} - {n} session{n === 1 ? "" : "s"}
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
  const picker = useRef<HTMLInputElement>(null);
  const [notice, setNotice] = useState("");
  const sessions = p.conversations.filter(c => c.projectId === pr.id);

  const addFiles = async (list: FileList | null) => {
    if (!list) return;
    const added = [];
    const errors: string[] = [];
    for (const f of Array.from(list)) {
      const r = await readProjectFile(f);
      if (typeof r === "string") errors.push(r); else added.push(r);
    }
    if (added.length) p.onUpdate(pr.id, { files: [...(pr.files ?? []), ...added] });
    setNotice(errors.join("\n"));
  };

  const linkFolder = async () => {
    const dir = await window.herama?.pickFolder();
    if (dir) p.onUpdate(pr.id, { dir });
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
        <span style={{ flex: 1 }}>Files</span>
        <button style={ghostBtn} onClick={() => picker.current?.click()}>Add files</button>
        <input ref={picker} type="file" multiple hidden onChange={e => { void addFiles(e.target.files); e.target.value = ""; }} />
      </div>
      {(pr.files ?? []).length === 0 && <Empty text="No files. Add text, code or notes the model should know about." />}
      {(pr.files ?? []).map(f => (
        <div key={f.id} style={{ ...card, display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ flex: 1, fontSize: 13, wordBreak: "break-all" }}>{f.name}</span>
          <span style={{ fontSize: 11, color: "var(--text-dim)" }}>{kb(f.size)}</span>
          <button style={{ ...ghostBtn, color: "var(--red)" }}
            onClick={() => p.onUpdate(pr.id, { files: (pr.files ?? []).filter(x => x.id !== f.id) })}>Remove</button>
        </div>
      ))}
      {notice && <div style={{ color: "var(--red)", fontSize: 12, whiteSpace: "pre-wrap" }}>{notice}</div>}

      <div style={label}>Linked folder (optional)</div>
      <div style={{ ...card, display: "flex", alignItems: "center", gap: 10 }}>
        <span style={{ flex: 1, fontSize: 12, color: "var(--text-mid)", wordBreak: "break-all" }}>{pr.dir || "None. Used by the file browser and terminal."}</span>
        <button style={ghostBtn} onClick={() => void linkFolder()}>{pr.dir ? "Change" : "Link folder"}</button>
        {pr.dir && <button style={ghostBtn} onClick={() => p.onUpdate(pr.id, { dir: undefined })}>Unlink</button>}
      </div>

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
