import { useEffect, useRef, useState } from "react";
import type { Agent, Conversation, Project } from "../../types";
import { projectFolders } from "../../util";
import Modal from "../Modal";
import type { ChatMsg } from "../../api";
import { splitThink } from "../../util";
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
  onCreate: (name: string, folders: string[], r: { description?: string; instructions?: string }) => void;
  onStartCreate: () => void;
  onUpdate: (id: string, patch: Partial<Project>) => void;
  assist: (messages: ChatMsg[], signal: AbortSignal) => AsyncGenerator<string>;
  onOpenConv: (id: string) => void;
  onNewSession: (projectId: string) => void;
  onRemove: (id: string) => void;
}

const input: React.CSSProperties = {
  width: "100%", background: "var(--bg2)", border: "1px solid var(--border)", borderRadius: 8,
  padding: "8px 12px", color: "var(--text)", fontSize: 13,
};
const label: React.CSSProperties = { fontSize: 12, color: "var(--text-dim)", margin: "16px 0 6px", textTransform: "uppercase", letterSpacing: "0.08em" };

function NewProject(p: { onClose: () => void; assist: Props["assist"]; onCreate: (name: string, folders: string[], r: Result) => void }) {
  const [wizard, setWizard] = useState(false);
  const [name, setName] = useState("");
  const [folders, setFolders] = useState<string[]>([]);
  const add = async () => {
    const d = await window.herama?.pickFolder();
    if (d && !folders.includes(d)) setFolders([...folders, d]);
  };
  if (wizard) return <SetupWizard name={name.trim()} folders={folders} assist={p.assist} onClose={p.onClose} onDone={r => p.onCreate(name.trim(), folders, r)} />;
  return (
    <Modal title="New project" onClose={p.onClose}>
      <div style={{ ...label, marginTop: 0 }}>Name</div>
      <input style={input} autoFocus value={name} onChange={e => setName(e.target.value)} />
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
        <button style={primaryBtn} disabled={!name.trim()} onClick={() => setWizard(true)}>Next</button>
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
      {p.creating && <NewProject onClose={p.onCloseCreate} assist={p.assist} onCreate={p.onCreate} />}
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
      <ProjectAssistant key={pr.id} project={pr} assist={p.assist} onUpdate={p.onUpdate} />
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

const fence = (tag: string) => new RegExp("```" + tag + "\\s*([\\s\\S]*?)```");
const KICKOFF = "Help me set up this project.";

interface Result { description?: string; instructions?: string }

/** Chat with the model. When it emits a fenced block named `tag` holding JSON, `onResult` receives it. */
function AssistantChat(p: { assist: Props["assist"]; system: () => string; tag: string; kickoff: boolean; onResult: (r: Result) => void }) {
  const [msgs, setMsgs] = useState<ChatMsg[]>([]);
  const [text, setText] = useState("");
  const [live, setLive] = useState("");
  const [busy, setBusy] = useState(false);
  const ctrl = useRef<AbortController | null>(null);
  const started = useRef(false);
  const block = fence(p.tag);

  const run = async (history: ChatMsg[]) => {
    const c = new AbortController();
    ctrl.current = c;
    setBusy(true);
    setLive("");
    let out = "";
    try {
      for await (const piece of p.assist([{ role: "system", content: p.system() }, ...history], c.signal)) {
        out += piece;
        setLive(splitThink(out).answer);
      }
    } catch (e) {
      if (!(e instanceof DOMException && e.name === "AbortError")) out += `${out ? "\n" : ""}[error] ${String(e)}`;
    }
    const answer = splitThink(out).answer;
    if (answer) setMsgs([...history, { role: "assistant", content: answer }]);
    setLive("");
    setBusy(false);
    ctrl.current = null;
    const m = answer.match(block);
    if (m) {
      try { p.onResult(JSON.parse(m[1]) as Result); } catch { /* ignore malformed block */ }
    }
  };

  useEffect(() => {
    if (started.current || !p.kickoff) return;
    started.current = true;
    void run([{ role: "user", content: KICKOFF }]);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const send = () => {
    if (!text.trim() || busy) return;
    const history: ChatMsg[] = [...msgs, { role: "user", content: text.trim() }];
    setMsgs(history);
    setText("");
    void run(history);
  };

  const show = (m: ChatMsg) => m.content.replace(block, "(saved)").trim();
  const shown = msgs.filter((m, i) => !(i === 0 && m.content === KICKOFF));

  return (
    <div>
      <div style={{ maxHeight: 300, overflowY: "auto", display: "flex", flexDirection: "column", gap: 8 }}>
        {shown.length === 0 && !busy && <div style={{ fontSize: 12, color: "var(--text-dim)" }}>Tell the model what you want to change in the description or instructions.</div>}
        {shown.map((m, i) => (
          <div key={i} style={{ fontSize: 13, whiteSpace: "pre-wrap", alignSelf: m.role === "user" ? "flex-end" : "flex-start", background: m.role === "user" ? "var(--bg2)" : "transparent", borderRadius: 8, padding: m.role === "user" ? "6px 10px" : 0 }}>{show(m)}</div>
        ))}
        {busy && <div style={{ fontSize: 13, whiteSpace: "pre-wrap", color: "var(--text-mid)" }}>{show({ role: "assistant", content: live }) || "..."}</div>}
      </div>
      <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
        <textarea style={{ ...input, resize: "none", maxHeight: 140 }} rows={Math.min(5, text.split("\n").length)} value={text}
          placeholder="Reply to the assistant... (Enter to send, Shift+Enter for a new line)" onChange={e => setText(e.target.value)}
          onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send(); } }} />
        {busy
          ? <button style={ghostBtn} onClick={() => ctrl.current?.abort()}>Stop</button>
          : <button style={primaryBtn} disabled={!text.trim()} onClick={send}>Send</button>}
      </div>
    </div>
  );
}

const COMPACT = "Keep the saved text compact so it does not use much of the model's context: the description is one sentence, the instructions are at most about 150 words of short imperative lines.";

/** Editing chat on the project page: the model updates description and instructions from the conversation. */
function ProjectAssistant(p: { project: Project; assist: Props["assist"]; onUpdate: Props["onUpdate"] }) {
  const pr = p.project;
  const latest = useRef(pr);
  latest.current = pr;
  const system = () => {
    const c = latest.current;
    return `You help the user edit a project in an AI assistant workspace. Project name: ${c.name}. ` +
      `Linked folders: ${projectFolders(c).join(", ") || "none"}. ` +
      `Current description: ${c.description || "(empty)"}. Current instructions: ${c.instructions || "(empty)"}. ` +
      "Talk in the user's language. When the user asks for a change, reply with a short message plus a fenced block exactly like:\n" +
      "```project\n{\"description\": \"one sentence\", \"instructions\": \"full instructions\"}\n```\n" +
      `The block always contains the complete updated values. ${COMPACT}`;
  };
  return (
    <div style={{ ...card, marginBottom: 8 }}>
      <div style={{ fontSize: 12, color: "var(--text-dim)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 8 }}>Project assistant</div>
      <AssistantChat assist={p.assist} system={system} tag="project" kickoff={false}
        onResult={r => p.onUpdate(pr.id, { ...(r.description ? { description: r.description } : {}), ...(r.instructions ? { instructions: r.instructions } : {}) })} />
    </div>
  );
}

/** Guided setup: description, then structure and instructions, then the project is created from what was agreed. */
function SetupWizard(p: { name: string; folders: string[]; assist: Props["assist"]; onDone: (r: Result) => void; onClose: () => void }) {
  const [tree, setTree] = useState<string | null>(null);
  useEffect(() => {
    (async () => {
      const k = p.folders.length && window.herama?.fsKnowledge ? await window.herama.fsKnowledge(p.folders, 0).catch(() => undefined) : undefined;
      setTree(k?.tree ?? "");
    })();
  }, [p.folders]);
  const system = () =>
    `You are setting up a new project called "${p.name}" in an AI assistant workspace together with the user. Talk in the user's language. ` +
    `Linked folders: ${p.folders.join(", ") || "none"}.${tree ? ` File tree:\n${tree.slice(0, 4000)}\n` : ""}\n` +
    "Follow these steps, one at a time, with short messages: " +
    "1) Ask the user to describe the project. Restate it in one sentence and ask them to confirm. " +
    "2) Ask about the project structure and how the assistant should behave (rules, tone, conventions). Summarize and ask them to confirm. " +
    "3) Keep going until the user explicitly approves. Only after the user approves, reply with a short closing message and the final block exactly like:\n" +
    "```final_project\n{\"description\": \"one sentence\", \"instructions\": \"instructions\"}\n```\n" +
    `Never output the block before approval. ${COMPACT}`;
  return (
    <Modal title={`Set up "${p.name}"`} onClose={p.onClose}>
      {tree === null ? <div style={{ fontSize: 12, color: "var(--text-dim)" }}>Reading folders...</div>
        : <AssistantChat assist={p.assist} system={system} tag="final_project" kickoff onResult={p.onDone} />}
      <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 14 }}>
        <button style={ghostBtn} onClick={() => p.onDone({})}>Skip setup</button>
      </div>
    </Modal>
  );
}
