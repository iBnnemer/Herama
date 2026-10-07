import { useState } from "react";
import type { Agent, Group } from "../types";
import { createGroup, updateGroup, deleteGroup } from "../api";
import Modal from "./Modal";

interface Props { group?: Group; agents: Agent[]; onClose: () => void; onSaved: () => void }

const inp: React.CSSProperties = {
  width: "100%", background: "var(--bg2)", border: "1px solid var(--border)",
  borderRadius: 8, padding: "8px 12px", color: "var(--text)", fontSize: 13, marginBottom: 12,
};

export default function GroupModal({ group, agents, onClose, onSaved }: Props) {
  const [name, setName] = useState(group?.name ?? "");
  const [lead, setLead] = useState(group?.lead ?? agents[0]?.id ?? "");
  const [members, setMembers] = useState<string[]>(group?.members ?? []);
  const [error, setError] = useState("");

  const toggle = (id: string) => setMembers(m => m.includes(id) ? m.filter(x => x !== id) : [...m, id]);

  const save = async () => {
    if (!name.trim()) { setError("name is required"); return; }
    if (!lead) { setError("choose a lead"); return; }
    try {
      const body = { name, lead, members: members.filter(m => m !== lead) };
      if (group) await updateGroup(group.id, body); else await createGroup(body);
      onSaved();
    } catch (e) { setError(String(e)); }
  };

  const del = async () => {
    if (!group || !confirm(`delete "${group.name}"?`)) return;
    await deleteGroup(group.id); onSaved();
  };

  return (
    <Modal title={group ? "edit group" : "new group"} onClose={onClose}>
      <label style={{ fontSize: 11, color: "var(--text-dim)" }}>name</label>
      <input style={inp} value={name} onChange={e => setName(e.target.value)} placeholder="My team" />
      <label style={{ fontSize: 11, color: "var(--text-dim)" }}>lead (receives your messages and delegates to the members)</label>
      <select style={inp} value={lead} onChange={e => setLead(e.target.value)}>
        {agents.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
      </select>
      <label style={{ fontSize: 11, color: "var(--text-dim)" }}>members</label>
      <div style={{ ...inp, maxHeight: 150, overflow: "auto" }}>
        {agents.filter(a => a.id !== lead).map(a => (
          <label key={a.id} style={{ display: "flex", gap: 8, alignItems: "center", padding: "3px 0", cursor: "pointer" }}>
            <input type="checkbox" checked={members.includes(a.id)} onChange={() => toggle(a.id)} />
            <span>{a.name}</span>
          </label>
        ))}
        {agents.length < 2 && <span style={{ color: "var(--text-dim)", fontSize: 12 }}>create more bots first</span>}
      </div>
      {error && <div style={{ color: "var(--red)", fontSize: 12, marginBottom: 10 }}>{error}</div>}
      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
        {group && <button onClick={del} style={{ marginRight: "auto", color: "var(--red)", fontSize: 12, padding: "7px 12px", border: "1px solid var(--red)", borderRadius: 8 }}>delete</button>}
        <button onClick={onClose} style={{ padding: "7px 16px", border: "1px solid var(--border)", borderRadius: 8, color: "var(--text-mid)", fontSize: 13 }}>cancel</button>
        <button onClick={save} style={{ padding: "7px 16px", background: "var(--accent)", color: "#000", borderRadius: 8, fontWeight: 600, fontSize: 13 }}>save</button>
      </div>
    </Modal>
  );
}
