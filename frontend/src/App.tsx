import { useState, useEffect, useCallback, useMemo } from "react";
import type { Mode, AppState, Agent, Model, Conversation, PanelId, Task, TaskStatus, TaskApi } from "./types";
import { fetchHealth, fetchModels, fetchAgents } from "./api";
import Sidebar from "./components/Sidebar";
import ChatView from "./components/ChatView";
import Dock from "./components/Dock";

const POLL_MS = 4000;
const LAYOUT_KEY = "herama.layout";

let _cid = 0;
const newConv = (agentId?: string): Conversation => ({
  id: String(++_cid),
  title: "new conversation",
  messages: [],
  agentId,
});

interface Layout { leftOpen: boolean; panels: PanelId[]; dockWidth: number }

function loadLayout(): Layout {
  const def: Layout = { leftOpen: true, panels: ["tasks", "files"], dockWidth: 380 };
  try {
    const raw = localStorage.getItem(LAYOUT_KEY);
    return raw ? { ...def, ...JSON.parse(raw) } : def;
  } catch { return def; }
}

export default function App() {
  const [mode, setMode] = useState<Mode>("chat");
  const [state, setState] = useState<AppState>({
    connected: false, tps: 0, models: [], agents: [],
    activeModel: "", contextLength: 4096, effort: "medium",
  });
  const [conversations, setConversations] = useState<Conversation[]>([newConv()]);
  const [activeConvId, setActiveConvId] = useState<string>(conversations[0].id);
  const [layout, setLayout] = useState<Layout>(loadLayout);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [projectDir, setProjectDir] = useState("");

  useEffect(() => {
    try { localStorage.setItem(LAYOUT_KEY, JSON.stringify(layout)); } catch { /* storage unavailable */ }
  }, [layout]);

  useEffect(() => { window.herama?.defaultDir().then(setProjectDir).catch(() => {}); }, []);

  const taskApi: TaskApi = useMemo(() => ({
    start: (label: string) => {
      const id = `${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
      const task: Task = { id, label, status: "running", ts: Date.now() };
      setTasks(prev => [task, ...prev].slice(0, 100));
      return id;
    },
    finish: (id: string, status: TaskStatus) =>
      setTasks(prev => prev.map(t => t.id === id ? { ...t, status } : t)),
  }), []);

  const togglePanel = (id: PanelId) =>
    setLayout(l => ({ ...l, panels: l.panels.includes(id) ? l.panels.filter(x => x !== id) : [...l.panels, id] }));

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
      {layout.leftOpen && (
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
      )}
      <ChatView
        conv={activeConv}
        state={state}
        onConvUpdate={p => updateConv(activeConv.id, p)}
        onNewConv={createConv}
        onModelChange={m => setState(s => ({ ...s, activeModel: m }))}
        onContextChange={n => setState(s => ({ ...s, contextLength: n }))}
        onEffortChange={e => setState(s => ({ ...s, effort: e }))}
        onTps={t => setState(s => ({ ...s, tps: t }))}
        leftOpen={layout.leftOpen}
        onToggleLeft={() => setLayout(l => ({ ...l, leftOpen: !l.leftOpen }))}
        openPanels={layout.panels}
        onTogglePanel={togglePanel}
        taskApi={taskApi}
      />
      <Dock
        open={layout.panels}
        width={layout.dockWidth}
        onWidth={w => setLayout(l => ({ ...l, dockWidth: w }))}
        onClose={togglePanel}
        tasks={tasks}
        taskApi={taskApi}
        onClearTasks={() => setTasks(t => t.filter(x => x.status === "running"))}
        projectDir={projectDir}
        onProjectDir={setProjectDir}
      />
    </div>
  );
}
