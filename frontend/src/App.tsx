import { useState, useEffect, useCallback, useRef } from "react";
import type { Mode, AppState, Agent, Model, Conversation, Effort } from "./types";
import { fetchHealth, fetchModels, fetchAgents } from "./api";
import Sidebar from "./components/Sidebar";
import ChatView from "./components/ChatView";

const POLL_MS = 4000;

let _cid = 0;
const newConv = (agentId?: string): Conversation => ({
  id: String(++_cid),
  title: "new conversation",
  messages: [],
  agentId,
});

export default function App() {
  const [mode, setMode] = useState<Mode>("chat");
  const [state, setState] = useState<AppState>({
    connected: false, tps: 0, models: [], agents: [],
    activeModel: "", contextLength: 4096, effort: "balanced",
  });
  const [conversations, setConversations] = useState<Conversation[]>([newConv()]);
  const [activeConvId, setActiveConvId] = useState<string>(conversations[0].id);

  const poll = useCallback(async () => {
    const connected = await fetchHealth();
    if (!connected) { setState(s => ({ ...s, connected: false })); return; }
    const [mr, ar] = await Promise.allSettled([fetchModels(), fetchAgents()]);
    setState(s => {
      const models: Model[] = mr.status === "fulfilled" ? mr.value : s.models;
      const agents: Agent[] = ar.status === "fulfilled" ? ar.value : s.agents;
      return { ...s, connected, models, agents, activeModel: s.activeModel || models[0]?.name || "" };
    });
  }, []);

  useEffect(() => { poll(); const t = setInterval(poll, POLL_MS); return () => clearInterval(t); }, [poll]);

  const createConv = (agentId?: string) => {
    const c = newConv(agentId);
    setConversations(prev => [c, ...prev]);
    setActiveConvId(c.id);
    return c;
  };

  const updateConv = (id: string, patch: Partial<Conversation>) =>
    setConversations(prev => prev.map(c => c.id === id ? { ...c, ...patch } : c));

  const activeConv = conversations.find(c => c.id === activeConvId) ?? conversations[0];

  return (
    <div style={{ display: "flex", width: "100%", height: "100%", overflow: "hidden" }}>
      <Sidebar
        mode={mode}
        onModeChange={m => { setMode(m); if (m === "chat") createConv(); }}
        conversations={conversations.filter(c => !c.agentId)}
        agentConvs={conversations.filter(c => !!c.agentId)}
        activeConvId={activeConvId}
        onSelectConv={setActiveConvId}
        onNewConv={() => createConv()}
        agents={state.agents}
        connected={state.connected}
        tps={state.tps}
        onRefreshAgents={poll}
      />
      <ChatView
        conv={activeConv}
        state={state}
        onConvUpdate={p => updateConv(activeConv.id, p)}
        onNewConv={createConv}
        onModelChange={m => setState(s => ({ ...s, activeModel: m }))}
        onContextChange={n => setState(s => ({ ...s, contextLength: n }))}
        onEffortChange={e => setState(s => ({ ...s, effort: e }))}
        onTps={t => setState(s => ({ ...s, tps: t }))}
      />
    </div>
  );
}
