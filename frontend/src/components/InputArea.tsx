import { useRef, useState } from "react";
import type { ClipboardEvent, DragEvent, KeyboardEvent } from "react";
import type { Agent, Attachment, Effort, Model, Project, Safety, Tune } from "../types";
import Dropdown from "./Dropdown";
import ModelPicker from "./ModelPicker";
import { readAttachment } from "../util";
import EffortPicker from "./EffortPicker";
import SettingsModal from "./SettingsModal";
import Icon from "./Icons";

interface Props {
  models: Model[];
  activeModel: string;
  effort: Effort;
  contextLength: number;
  tps: number;
  streaming: boolean;
  queue: string[];
  onRemoveQueued: (i: number) => void;
  onSend: (text: string, atts: Attachment[]) => void;
  onStop: () => void;
  onModelChange: (m: string) => void;
  onEffortChange: (e: Effort) => void;
  onManageModels: () => void;
  safety: Safety;
  onSafetyChange: (s: Safety) => void;
  projects: Project[];
  projectId?: string;
  onProject: (id: string) => void;
  agents: Agent[];
  agentName?: string;
  onAgent: (id: string) => void;
  onContextChange: (n: number, tune?: Tune) => void;
  disabled: boolean;
  placeholder?: string;
}

const shortName = (n: string) => n.replace(/:latest$/, "");
const SAFETY = [
  { id: "ask", label: "Ask", hint: "Ask for approval before running commands" },
  { id: "plan", label: "Plan", hint: "Plan first: the model proposes steps and runs nothing" },
  { id: "auto", label: "Auto", hint: "Run commands without asking" },
  { id: "off", label: "Off", hint: "No commands or actions at all" },
];

export default function InputArea(p: Props) {
  const ref = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const [showSettings, setShowSettings] = useState(false);
  const [hasText, setHasText] = useState(false);
  const [atts, setAtts] = useState<Attachment[]>([]);
  const [notice, setNotice] = useState("");

  const addFiles = async (files: File[]) => {
    for (const f of files) {
      const r = await readAttachment(f);
      if (typeof r === "string") setNotice(r);
      else { setNotice(""); setAtts(a => [...a, r]); }
    }
  };

  const send = () => {
    const text = ref.current?.value.trim() ?? "";
    if ((!text && atts.length === 0) || p.disabled) return;
    p.onSend(text, atts);
    if (ref.current) { ref.current.value = ""; ref.current.style.height = "auto"; }
    setHasText(false);
    setAtts([]);
    setNotice("");
  };

  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send(); }
    else if (e.key === "Escape" && p.streaming) p.onStop();
  };

  const onPaste = (e: ClipboardEvent<HTMLTextAreaElement>) => {
    const files = Array.from(e.clipboardData.files);
    if (files.length) { e.preventDefault(); void addFiles(files); }
  };

  const onDrop = (e: DragEvent) => {
    const files = Array.from(e.dataTransfer.files);
    if (files.length) { e.preventDefault(); void addFiles(files); }
  };

  const canSend = (hasText || atts.length > 0) && !p.disabled;
  const showStop = p.streaming && !canSend;
  const chip: React.CSSProperties = {
    background: "transparent", border: "none", borderRadius: 8, padding: "4px 8px",
    color: "var(--text-mid)", fontSize: 12, cursor: "pointer",
  };

  return (
    <div style={{ padding: "0 16px 18px", flexShrink: 0, maxWidth: 780, width: "100%", margin: "0 auto" }}>
      {p.queue.length > 0 && (
        <div style={{ marginBottom: 8, display: "flex", flexDirection: "column", gap: 4 }}>
          {p.queue.map((q, i) => (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: "var(--text-mid)", background: "var(--surface)", border: "1px dashed var(--border2)", borderRadius: 10, padding: "5px 10px" }}>
              <span style={{ color: "var(--text-dim)" }}>queued</span>
              <span dir="auto" style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{q}</span>
              <button onClick={() => p.onRemoveQueued(i)} title="remove" style={{ color: "var(--text-dim)", display: "flex" }}><Icon name="close" size={12} /></button>
            </div>
          ))}
        </div>
      )}

      <div style={{ display: "flex", justifyContent: "flex-end", alignItems: "center", gap: 4, marginBottom: 6 }}>
        <ModelPicker models={p.models} active={p.activeModel} contextLength={p.contextLength} onPick={p.onModelChange} onManage={p.onManageModels} />
        <button onClick={() => setShowSettings(true)}
          title={`context and generation settings (ctx ${p.contextLength >= 1024 ? `${Math.round(p.contextLength / 1024)}K` : p.contextLength})`}
          style={{ ...chip, display: "flex", padding: 6 }}><Icon name="gear" size={16} /></button>
      </div>

      <div onDragOver={e => e.preventDefault()} onDrop={onDrop} style={{
        background: "var(--surface)", border: "1px solid var(--border2)", borderRadius: 18,
        boxShadow: "0 2px 12px rgba(0,0,0,0.3)", padding: "10px 10px 8px 14px",
      }}>
        {atts.length > 0 && (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, padding: "2px 0 8px" }}>
            {atts.map(a => (
              <div key={a.id} style={{ position: "relative", border: "1px solid var(--border2)", borderRadius: 10, overflow: "hidden", background: "var(--bg2)" }}>
                {a.kind === "image"
                  ? <img src={a.dataUrl} alt={a.name} style={{ display: "block", height: 64, maxWidth: 120, objectFit: "cover" }} />
                  : <div style={{ padding: "8px 12px", fontSize: 12, color: "var(--text-mid)", maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{a.name}</div>}
                <button onClick={() => setAtts(l => l.filter(x => x.id !== a.id))} title="remove" style={{
                  position: "absolute", top: 3, right: 3, width: 18, height: 18, borderRadius: "50%",
                  background: "rgba(0,0,0,0.7)", color: "#fff", display: "flex", alignItems: "center", justifyContent: "center",
                }}><Icon name="close" size={10} /></button>
              </div>
            ))}
          </div>
        )}
        <div style={{ display: "flex", alignItems: "flex-end", gap: 8 }}>
          <textarea
            ref={ref}
            dir="auto"
            placeholder={p.placeholder ?? "message herama..."}
            rows={1}
            onKeyDown={onKey}
            onPaste={onPaste}
            onInput={e => {
              const t = e.currentTarget;
              t.style.height = "auto";
              t.style.height = Math.min(t.scrollHeight, 200) + "px";
              setHasText(t.value.trim().length > 0);
            }}
            style={{
              flex: 1, padding: "6px 4px", fontSize: 15, lineHeight: 1.5, minHeight: 32,
              maxHeight: 200, background: "transparent", color: "var(--text)", display: "block",
            }}
          />
          <button onClick={showStop ? p.onStop : send} disabled={!showStop && !canSend}
            title={showStop ? "stop (Esc)" : p.streaming ? "add to queue" : "send"} style={{
              width: 32, height: 32, borderRadius: 10, flexShrink: 0,
              background: showStop || canSend ? "var(--accent)" : "var(--surface2)",
              color: showStop || canSend ? "#000" : "var(--text-dim)",
              display: "flex", alignItems: "center", justifyContent: "center",
            }}><Icon name={showStop ? "stop" : "send"} size={16} /></button>
        </div>
        {notice && <div style={{ fontSize: 11, color: "var(--red)", padding: "2px 4px" }}>{notice}</div>}
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 8, padding: "0 4px" }}>
        <input ref={fileRef} type="file" multiple hidden onChange={e => { void addFiles(Array.from(e.target.files ?? [])); e.target.value = ""; }} />
        <button onClick={() => fileRef.current?.click()} title="add files or images (or paste with Ctrl+V)"
          style={{ ...chip, display: "flex", padding: 6 }}><Icon name="plus" size={16} /></button>
        <Dropdown tinted title="project" icon={<Icon name="box" size={13} />}
          label={p.projects.find(x => x.id === p.projectId)?.name ?? "No project"} value={p.projectId ?? ""} onPick={p.onProject}
          items={[{ id: "", label: "No project" }, ...p.projects.map(x => ({ id: x.id, label: x.name }))]} />
        <Dropdown tinted title="agent" icon={<Icon name="bolt" size={13} />}
          label={p.agentName ?? "default"} value={p.agents.find(a => a.name === p.agentName)?.id ?? ""} onPick={p.onAgent}
          items={[{ id: "", label: "default" }, ...p.agents.map(a => ({ id: a.id, label: a.name }))]} />
        <Dropdown tinted title="commands and safety" icon={<Icon name="shield" size={13} />}
          label={SAFETY.find(x => x.id === p.safety)?.label ?? "Plan"} value={p.safety}
          onPick={id => p.onSafetyChange(id as Safety)} items={SAFETY} />
        <span style={{ marginLeft: "auto" }} />
        <EffortPicker effort={p.effort} onChange={p.onEffortChange} />
      </div>

      {showSettings && (
        <SettingsModal model={p.activeModel} contextLength={p.contextLength} tps={p.tps} onApply={p.onContextChange} onClose={() => setShowSettings(false)} />
      )}
    </div>
  );
}
