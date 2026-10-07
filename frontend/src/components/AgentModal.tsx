import { useRef, useState } from "react";
import type { Agent } from "../types";
import { createAgent, updateAgent, deleteAgent } from "../api";
import type { ChatMsg } from "../api";
import { splitThink } from "../util";
import Modal from "./Modal";

interface Props {
  agent?: Agent;
  models: { name: string }[];
  assist: (messages: ChatMsg[], signal: AbortSignal) => AsyncGenerator<string>;
  onClose: () => void;
  onSaved: () => void;
}

const inp: React.CSSProperties = {
  width: "100%", background: "var(--bg2)", border: "1px solid var(--border)",
  borderRadius: 8, padding: "8px 12px", color: "var(--text)", fontSize: 13, marginBottom: 12,
};
const lbl: React.CSSProperties = { fontSize: 11, color: "var(--text-dim)" };
const bare = (n: string) => n.replace(/:latest$/, "");

type Tab = "general" | "soul" | "agent";
const TABS: { id: Tab; label: string }[] = [{ id: "general", label: "General" }, { id: "soul", label: "SOUL" }, { id: "agent", label: "AGENT" }];

const FILE_HELP: Record<"soul" | "agent", { name: string; about: string; seed: string }> = {
  soul: { name: "SOUL", about: "Who this agent is: character, values, tone and how it speaks.", seed: "Character: \nValues: \nTone: \n" },
  agent: { name: "AGENT", about: "How this agent works: its duties, rules and step-by-step procedures.", seed: "Role: \nRules: \nProcedure: \n" },
};

export default function AgentModal({ agent, models, assist, onClose, onSaved }: Props) {
  const [tab, setTab] = useState<Tab>("general");
  const [name, setName] = useState(agent?.name ?? "");
  const [system, setSystem] = useState(agent?.system_prompt ?? "");
  const [model, setModel] = useState(agent?.model ?? "");
  const [soul, setSoul] = useState(agent?.soul ?? "");
  const [instr, setInstr] = useState(agent?.instructions ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [ask, setAsk] = useState("");
  const [busy, setBusy] = useState(false);
  const [undo, setUndo] = useState<{ tab: Tab; text: string } | null>(null);
  const abort = useRef<AbortController | null>(null);

  const missing = !!model && !models.some(m => bare(m.name) === bare(model));

  const save = async () => {
    if (!name.trim()) { setError("name is required"); setTab("general"); return; }
    setSaving(true); setError("");
    const body = { name, system_prompt: system, model, soul, instructions: instr };
    try {
      agent?.id ? await updateAgent(agent.id, body) : await createAgent(body);
      onSaved();
    } catch (e) { setError(String(e)); }
    finally { setSaving(false); }
  };

  const del = async () => {
    if (!agent?.id || !confirm(`delete "${agent.name}"?`)) return;
    await deleteAgent(agent.id); onSaved();
  };

  /** Let the model rewrite the open file following the request typed below it. */
  const improve = async () => {
    const which = tab === "soul" ? "soul" : "agent";
    const cur = which === "soul" ? soul : instr;
    const help = FILE_HELP[which];
    const request = ask.trim() || "Improve it: make it clearer, more specific and better organised.";
    const c = new AbortController();
    abort.current = c;
    setBusy(true); setError("");
    let out = "";
    try {
      const sys = `You edit the ${help.name} text of an AI agent named "${name || "agent"}". ${help.about} Apply the user's request to the current content and reply with the complete new text and nothing else (no explanations, no code fences). Keep the language of the current content unless asked otherwise.`;
      const user = `Current ${help.name} text:\n"""\n${cur || help.seed}\n"""\n\nRequest: ${request}`;
      for await (const piece of assist([{ role: "system", content: sys }, { role: "user", content: user }], c.signal)) out += piece;
      let text = splitThink(out).answer.trim();
      text = text.replace(/^```(?:markdown|md)?\s*\n/, "").replace(/\n```$/, "").trim();
      if (!text) throw new Error("the model returned nothing");
      setUndo({ tab, text: cur });
      (which === "soul" ? setSoul : setInstr)(text);
      setAsk("");
    } catch (e) {
      if (!c.signal.aborted) setError(String((e as Error).message ?? e));
    } finally { setBusy(false); abort.current = null; }
  };

  const fileTab = (which: "soul" | "agent") => {
    const help = FILE_HELP[which];
    const value = which === "soul" ? soul : instr;
    const set = which === "soul" ? setSoul : setInstr;
    return (
      <>
        <div style={{ fontSize: 12, color: "var(--text-dim)", marginBottom: 8 }}>{help.about} Saved with the agent and added to every conversation it has.</div>
        <textarea style={{ ...inp, minHeight: 190, resize: "vertical", fontSize: 13, marginBottom: 8 }} value={value}
          onChange={e => set(e.target.value)} placeholder={help.seed} spellCheck={false} />
        <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
          <input style={{ ...inp, marginBottom: 0, flex: 1 }} value={ask} onChange={e => setAsk(e.target.value)} disabled={busy}
            placeholder="Ask the model to edit this text (empty = improve it)" onKeyDown={e => { if (e.key === "Enter" && !busy) void improve(); }} />
          {busy
            ? <button onClick={() => abort.current?.abort()} style={{ padding: "7px 14px", border: "1px solid var(--border)", borderRadius: 8, fontSize: 13, color: "var(--text-mid)" }}>Stop</button>
            : <button onClick={() => void improve()} style={{ padding: "7px 14px", border: "1px solid var(--accent)", borderRadius: 8, fontSize: 13, color: "var(--accent)", whiteSpace: "nowrap" }}>Edit with model</button>}
          {undo && undo.tab === tab && !busy && (
            <button onClick={() => { (which === "soul" ? setSoul : setInstr)(undo.text); setUndo(null); }} style={{ padding: "7px 12px", border: "1px solid var(--border)", borderRadius: 8, fontSize: 13, color: "var(--text-mid)" }}>Undo</button>
          )}
        </div>
        {busy && <div style={{ fontSize: 12, color: "var(--text-dim)", marginBottom: 8 }}>The model is writing...</div>}
      </>
    );
  };

  return (
    <Modal title={agent ? "edit agent" : "new agent"} onClose={onClose}>
      <div style={{ display: "flex", gap: 2, marginBottom: 14, borderBottom: "1px solid var(--border)" }}>
        {TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)} style={{
            padding: "6px 12px", fontSize: 13, marginBottom: -1,
            color: tab === t.id ? "var(--text)" : "var(--text-dim)", borderBottom: `2px solid ${tab === t.id ? "var(--accent)" : "transparent"}`,
          }}>{t.label}{t.id === "soul" && soul.trim() ? " *" : t.id === "agent" && instr.trim() ? " *" : ""}</button>
        ))}
      </div>

      {tab === "general" && (
        <>
          <label style={lbl}>name</label>
          <input style={inp} value={name} onChange={e => setName(e.target.value)} placeholder="My Agent" />
          <label style={lbl}>model</label>
          <select style={inp} value={model} onChange={e => setModel(e.target.value)}>
            <option value="">Default (any available model)</option>
            {missing && <option value={model}>{bare(model)} (not available)</option>}
            {models.map(m => <option key={m.name} value={m.name}>{m.name.startsWith("api:") ? `${bare(m.name).slice(4)} (API)` : bare(m.name)}</option>)}
          </select>
          {missing && <div style={{ fontSize: 12, color: "var(--accent)", margin: "-6px 0 12px" }}>This model is no longer available, so the agent uses the selected model instead.</div>}
          <label style={lbl}>system prompt</label>
          <textarea style={{ ...inp, minHeight: 90, resize: "vertical" as const }} value={system} onChange={e => setSystem(e.target.value)} placeholder="you are a helpful assistant..." />
        </>
      )}
      {tab === "soul" && fileTab("soul")}
      {tab === "agent" && fileTab("agent")}

      {error && <div style={{ color: "var(--red)", fontSize: 12, marginBottom: 10 }}>{error}</div>}
      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
        {agent && agent.id !== "default" && <button onClick={del} style={{ marginRight: "auto", color: "var(--red)", fontSize: 12, padding: "7px 12px", border: "1px solid var(--red)", borderRadius: 8 }}>delete</button>}
        <button onClick={onClose} style={{ padding: "7px 16px", border: "1px solid var(--border)", borderRadius: 8, color: "var(--text-mid)", fontSize: 13 }}>cancel</button>
        <button onClick={save} disabled={saving || busy} style={{ padding: "7px 16px", background: "var(--accent)", color: "#000", borderRadius: 8, fontWeight: 600, fontSize: 13 }}>
          {saving ? "saving..." : "save"}
        </button>
      </div>
    </Modal>
  );
}
