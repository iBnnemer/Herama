import { useState, useCallback } from "react";
import type { AppState, Agent, Message } from "../types";
import { streamGenerate } from "../api";
import AgentModal from "./AgentModal";
import MessageList from "./MessageList";
import InputArea from "./InputArea";
import ModelBar from "./ModelBar";
import TopBar from "./TopBar";

interface Props {
  state: AppState;
  onModelChange: (m: string) => void;
  onContextChange: (n: number) => void;
  onTps: (t: number) => void;
  onRefreshAgents: () => void;
}

let _id = 0;
const uid = () => String(++_id);

export default function AgentsPanel({ state, onModelChange, onContextChange, onTps, onRefreshAgents }: Props) {
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [tokenCount, setTokenCount] = useState(0);
  const [showNew, setShowNew] = useState(false);

  const selectAgent = (a: Agent) => {
    setSelectedAgent(a);
    setMessages([]);
    setTokenCount(0);
  };

  const send = useCallback(async (text: string) => {
    if (streaming || !selectedAgent) return;
    const model = selectedAgent.model || state.activeModel;
    if (!model) return;

    const userMsg: Message = { id: uid(), role: "user", content: text, ts: Date.now() };
    const asstId = uid();
    const asstMsg: Message = { id: asstId, role: "assistant", content: "", ts: Date.now(), streaming: true };

    setMessages(prev => [...prev, userMsg, asstMsg]);
    setStreaming(true);

    const t0 = performance.now();
    let tokens = 0;
    let full = "";

    try {
      for await (const chunk of streamGenerate(model, text, selectedAgent.system_prompt, state.contextLength)) {
        full += chunk;
        tokens += chunk.split(/\s+/).length;
        const elapsed = (performance.now() - t0) / 1000;
        if (elapsed > 0.5) onTps(tokens / elapsed);
        setMessages(prev => prev.map(m => m.id === asstId ? { ...m, content: full } : m));
      }
    } finally {
      setMessages(prev => prev.map(m => m.id === asstId ? { ...m, streaming: false } : m));
      setStreaming(false);
      setTokenCount(c => c + tokens);
    }
  }, [streaming, selectedAgent, state.activeModel, state.contextLength, onTps]);

  return (
    <div style={{ display: "flex", height: "100%" }}>
      {/* Agent list */}
      <div style={{
        width: 200, borderRight: "1px solid var(--border)",
        display: "flex", flexDirection: "column", background: "var(--surface)",
      }}>
        <div style={{ padding: "10px 14px", borderBottom: "1px solid var(--border)", fontSize: 10, color: "var(--text-dim)", letterSpacing: "0.1em" }}>
          agents
        </div>
        <div style={{ flex: 1, overflow: "auto" }}>
          {state.agents.length === 0 && (
            <div style={{ padding: "12px 14px", color: "var(--text-dim)", fontSize: 11 }}>no agents yet</div>
          )}
          {state.agents.map(a => (
            <AgentRow
              key={a.id}
              agent={a}
              active={selectedAgent?.id === a.id}
              onClick={() => selectAgent(a)}
            />
          ))}
        </div>
        <button
          onClick={() => setShowNew(true)}
          style={{
            padding: "8px 14px", borderTop: "1px solid var(--border)",
            color: "var(--accent)", fontSize: 11, textAlign: "left",
            display: "flex", gap: 6, alignItems: "center",
          }}
        >
          <span>+</span><span>new agent</span>
        </button>
      </div>

      {/* Chat area */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column" }}>
        <TopBar
          title={selectedAgent ? `agent: ${selectedAgent.name}` : "select an agent"}
          connected={state.connected}
          tps={state.tps}
        />
        {selectedAgent ? (
          <>
            <MessageList messages={messages} />
            <ModelBar
              models={state.models}
              activeModel={selectedAgent.model || state.activeModel}
              contextLength={state.contextLength}
              tps={state.tps}
              onModelChange={onModelChange}
              onContextChange={onContextChange}
              tokenCount={tokenCount}
            />
            <InputArea
              onSend={send}
              disabled={streaming || !state.connected}
              placeholder={`message ${selectedAgent.name}…`}
            />
          </>
        ) : (
          <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--text-dim)", fontSize: 12 }}>
            select an agent from the list to start chatting
          </div>
        )}
      </div>

      {showNew && (
        <AgentModal
          onClose={() => setShowNew(false)}
          onSaved={() => { setShowNew(false); onRefreshAgents(); }}
        />
      )}
    </div>
  );
}

function AgentRow({ agent, active, onClick }: { agent: Agent; active: boolean; onClick: () => void }) {
  const [hov, setHov] = useState(false);
  return (
    <div
      onClick={onClick}
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      style={{
        padding: "7px 14px", cursor: "pointer", fontSize: 12,
        background: active ? "var(--surface2)" : hov ? "rgba(255,255,255,0.03)" : "transparent",
        borderLeft: active ? `2px solid var(--accent)` : "2px solid transparent",
        color: active ? "var(--text)" : "var(--text-mid)",
        display: "flex", alignItems: "center", gap: 6,
      }}
    >
      <span style={{ fontSize: 8, color: active ? "var(--accent)" : "var(--border2)" }}>●</span>
      <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{agent.name}</span>
    </div>
  );
}
