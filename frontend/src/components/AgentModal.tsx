import { useState } from "react";
import type { Agent } from "../types";
import { createAgent, updateAgent, deleteAgent } from "../api";
import Modal from "./Modal";

interface Props { agent?: Agent; onClose: () => void; onSaved: () => void }

const inp: React.CSSProperties = {
  width: "100%", background: "var(--bg2)", border: "1px solid var(--border)",
  borderRadius: 8, padding: "8px 12px", color: "var(--text)", fontSize: 13, marginBottom: 12,
};

export default function AgentModal({ agent, onClose, onSaved }: Props) {
  const [name, setName] = useState(agent?.name ?? "");
  const [system, setSystem] = useState(agent?.system_prompt ?? "");
  const [model, setModel] = useState(agent?.model ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const save = async () => {
    if (!name.trim()) { setError("name is required"); return; }
    setSaving(true); setError("");
    try {
      agent?.id ? await updateAgent(agent.id, { name, system_prompt: system, model })
                : await createAgent({ name, system_prompt: system, model });
      onSaved();
    } catch (e) { setError(String(e)); }
    finally { setSaving(false); }
  };

  const del = async () => {
    if (!agent?.id || !confirm(`delete "${agent.name}"?`)) return;
    await deleteAgent(agent.id); onSaved();
  };

  return (
    <Modal title={agent ? "edit agent" : "new agent"} onClose={onClose}>
      <label style={{ fontSize: 11, color: "var(--text-dim)" }}>name</label>
      <input style={inp} value={name} onChange={e => setName(e.target.value)} placeholder="My Agent" />
      <label style={{ fontSize: 11, color: "var(--text-dim)" }}>model (optional override)</label>
      <input style={inp} value={model} onChange={e => setModel(e.target.value)} placeholder="llama3.2:3b" />
      <label style={{ fontSize: 11, color: "var(--text-dim)" }}>system prompt</label>
      <textarea style={{ ...inp, minHeight: 90, resize: "vertical" as const }} value={system} onChange={e => setSystem(e.target.value)} placeholder="you are a helpful assistant…" />
      {error && <div style={{ color: "var(--red)", fontSize: 12, marginBottom: 10 }}>{error}</div>}
      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
        {agent && <button onClick={del} style={{ marginRight: "auto", color: "var(--red)", fontSize: 12, padding: "7px 12px", border: "1px solid var(--red)", borderRadius: 8 }}>delete</button>}
        <button onClick={onClose} style={{ padding: "7px 16px", border: "1px solid var(--border)", borderRadius: 8, color: "var(--text-mid)", fontSize: 13 }}>cancel</button>
        <button onClick={save} disabled={saving} style={{ padding: "7px 16px", background: "var(--accent)", color: "#000", borderRadius: 8, fontWeight: 600, fontSize: 13 }}>
          {saving ? "saving…" : "save"}
        </button>
      </div>
    </Modal>
  );
}
