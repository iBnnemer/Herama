import { useState, useEffect, useCallback } from "react";
import type { Mode, AppState, Agent, Model } from "./types";
import { fetchHealth, fetchModels, fetchAgents } from "./api";
import Sidebar from "./components/Sidebar";
import ChatPanel from "./components/ChatPanel";
import AgentsPanel from "./components/AgentsPanel";

const POLL_MS = 4000;

const DEFAULT_STATE: AppState = {
  connected: false,
  tps: 0,
  models: [],
  agents: [],
  activeModel: "",
  contextLength: 4096,
};

export default function App() {
  const [mode, setMode] = useState<Mode>("chat");
  const [state, setState] = useState<AppState>(DEFAULT_STATE);

  const poll = useCallback(async () => {
    const connected = await fetchHealth();
    if (!connected) { setState(s => ({ ...s, connected: false })); return; }
    const [models, agents] = await Promise.allSettled([fetchModels(), fetchAgents()]);
    setState(s => {
      const newModels: Model[] = models.status === "fulfilled" ? models.value : s.models;
      const newAgents: Agent[] = agents.status === "fulfilled" ? agents.value : s.agents;
      const activeModel = s.activeModel || newModels[0]?.name || "";
      return { ...s, connected, models: newModels, agents: newAgents, activeModel };
    });
  }, []);

  useEffect(() => {
    poll();
    const t = setInterval(poll, POLL_MS);
    return () => clearInterval(t);
  }, [poll]);

  const setActiveModel = (m: string) => setState(s => ({ ...s, activeModel: m }));
  const setContextLength = (n: number) => setState(s => ({ ...s, contextLength: n }));
  const setTps = (tps: number) => setState(s => ({ ...s, tps }));
  const refreshAgents = async () => {
    const agents = await fetchAgents();
    setState(s => ({ ...s, agents }));
  };

  return (
    <div style={{ display: "flex", width: "100%", height: "100%", overflow: "hidden" }}>
      <Sidebar
        mode={mode}
        onModeChange={setMode}
        connected={state.connected}
        tps={state.tps}
        agents={state.agents}
        onRefreshAgents={refreshAgents}
      />
      <main style={{ flex: 1, overflow: "hidden", display: "flex", flexDirection: "column" }}>
        {mode === "chat" ? (
          <ChatPanel
            state={state}
            onModelChange={setActiveModel}
            onContextChange={setContextLength}
            onTps={setTps}
          />
        ) : (
          <AgentsPanel
            state={state}
            onModelChange={setActiveModel}
            onContextChange={setContextLength}
            onTps={setTps}
            onRefreshAgents={refreshAgents}
          />
        )}
      </main>
    </div>
  );
}
