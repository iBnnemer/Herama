import { useState } from "react";
import type { Agent } from "../types";
import { createAgent, updateAgent, deleteAgent } from "../api";
import Modal from "./Modal";

interface Props {
  agent?: Agent;
  onClose: () => void;
  onSaved: () => void;
}

const inp: React.CSSProperties = {
  width: "100%", background: "var(--surface2)", border: "1px solid var(--border)",
  borderRadius: 4, padding: "6px 10px", color: "var(--text)", fontSize: 12, marginBottom: 10,
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
      if (agent?.id) {
        await updateAgent(agent.id, { name, system_prompt: system, model });
      } else {
        await createAgent({ name, system_prompt: system, model });
      }
      onSaved();
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  };

  const del = async () => {
    if (!agent?.id || !confirm(`delete agent "${agent.name}"?`)) return;
    await deleteAgent(agent.id);
    onSaved();
  };

  return (
    <Modal title={agent ? "edit agent" : "new agent"} onClose={onClose}>
      <label style={{ color: "var(--text-dim)", fontSize: 10 }}>name</label>
      <input style={inp} value={name} onChange={e => setName(e.target.value)} placeholder="agent name" />

      <label style={{ color: "var(--text-dim)", fontSize: 10 }}>model</label>
      <input style={inp} value={model} onChange={e => setModel(e.target.value)} placeholder="llama3.2:3b" />

      <label style={{ color: "var(--text-dim)", fontSize: 10 }}>system prompt</label>
      <textarea
        style={{ ...inp, minHeight: 80, resize: "vertical" as const }}
        value={system}
        onChange={e => setSystem(e.target.value)}
        placeholder="you are a helpful assistant…"
      />

      {error && <div style={{ color: "#ef4444", fontSize: 11, marginBottom: 8 }}>{error}</div>}

      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
        {agent && (
          <button onClick={del} style={{ marginRight: "auto", color: "#ef4444", fontSize: 11, padding: "6px 10px", border: "1px solid #ef4444", borderRadius: 4 }}>
            delete
          </button>
        )}
        <button onClick={onClose} style={{ padding: "6px 14px", border: "1px solid var(--border)", borderRadius: 4, color: "var(--text-mid)", fontSize: 12 }}>cancel</button>
        <button onClick={save} disabled={saving} style={{ padding: "6px 14px", background: "var(--accent)", color: "#000", borderRadius: 4, fontWeight: 600, fontSize: 12 }}>
          {saving ? "saving…" : "save"}
        </button>
      </div>
    </Modal>
  );
}
