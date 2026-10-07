import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import type {
  Mode, AppState, Agent, Model, Conversation, PanelId, Task, TaskStatus, TaskApi,
  View, Project, Job, InboxItem,
} from "./types";
import { EFFORT_PARAMS } from "./types";
import type { ChatMsg } from "./api";
import { fetchHealth, fetchModels, fetchAgents, streamChat, retryRuntime, approvedTune } from "./api";
import { projectFolders, rid, splitThink } from "./util";
import { usePersistent } from "./hooks/usePersistent";
import Sidebar from "./components/Sidebar";
import TopBar from "./components/TopBar";
import ChatView from "./components/ChatView";
import Dock from "./components/Dock";
import ProjectsPage from "./components/pages/ProjectsPage";
import CapabilitiesPage from "./components/pages/CapabilitiesPage";
import MessagingPage from "./components/pages/MessagingPage";
import ArtifactsPage from "./components/pages/ArtifactsPage";
import JobsPage from "./components/pages/JobsPage";

const POLL_MS = 4000;
const JOB_TICK_MS = 20_000;

const newConv = (opts: { agentId?: string; projectId?: string } = {}): Conversation => ({
  id: rid(), title: "New session", messages: [], ...opts,
});

const reviveConvs = (list: Conversation[]): Conversation[] => {
  const out = list.map(c => ({ ...c, messages: c.messages.map(m => ({ ...m, streaming: false })) }));
  return out.length ? out : [newConv()];
};

interface Layout { leftOpen: boolean; panels: PanelId[]; dockWidth: number }

const VIEW_TITLES: Record<Exclude<View, "chat">, string> = {
  projects: "Projects", capabilities: "Capabilities", messaging: "Messaging",
  artifacts: "Artifacts", jobs: "Scheduled jobs",
};

export default function App() {
  const [mode, setMode] = useState<Mode>("chat");
  const [view, setView] = useState<View>("chat");
  const [state, setState] = useState<AppState>({
    connected: false, engine: "", accelerated: null, runtime: null, tps: 0, models: [], agents: [],
    activeModel: "", contextLength: 65536, tune: {}, effort: "medium",
  });
  const [conversations, setConversations] = usePersistent<Conversation[]>("herama.convs", [newConv()], reviveConvs);
  const [activeConvId, setActiveConvId] = useState<string>(() => conversations[0].id);
  const [layout, setLayout] = usePersistent<Layout>("herama.layout", { leftOpen: true, panels: ["tasks", "files"], dockWidth: 380 });
  const [projects, setProjects] = usePersistent<Project[]>("herama.projects", []);
  const [jobs, setJobs] = usePersistent<Job[]>("herama.jobs", []);
  const [inbox, setInbox] = usePersistent<InboxItem[]>("herama.inbox", []);
  const [activeProjectId, setActiveProjectId] = useState("");
  const [openProjectId, setOpenProjectId] = useState("");
  const [tasks, setTasks] = useState<Task[]>([]);
  const [projectDir, setProjectDir] = useState("");

  useEffect(() => { window.herama?.defaultDir().then(setProjectDir).catch(() => {}); }, []);

  useEffect(() => {
    if (view === "messaging" && inbox.some(i => !i.read)) setInbox(list => list.map(i => ({ ...i, read: true })));
  }, [view, inbox, setInbox]);

  const taskApi: TaskApi = useMemo(() => ({
    start: (label: string) => {
      const id = rid();
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
    const health = await fetchHealth();
    if (!health) { setState(s => ({ ...s, connected: false })); return; }
    const connected = true;
    const engine = health.engine ?? "";
    const accelerated = typeof health.accelerated === "boolean" ? health.accelerated : null;
    const [mr, ar] = await Promise.allSettled([fetchModels(), fetchAgents()]);
    setState(s => {
      const models: Model[] = mr.status === "fulfilled" ? mr.value : s.models;
      const agents: Agent[] = ar.status === "fulfilled" ? ar.value : s.agents;
      return { ...s, connected, engine, accelerated, runtime: health.runtime ?? null, models, agents, activeModel: models.some(m => m.name === s.activeModel) ? s.activeModel : (models[0]?.name ?? "") };
    });
  }, []);

  useEffect(() => { poll(); const t = setInterval(poll, POLL_MS); return () => clearInterval(t); }, [poll]);

  const createConv = (opts: { agentId?: string; projectId?: string } = {}) => {
    const c = newConv(opts);
    setConversations(prev => [c, ...prev]);
    setActiveConvId(c.id);
    setView("chat");
    return c;
  };

  const updateConv = useCallback((id: string, patch: Partial<Conversation>) =>
    setConversations(prev => prev.map(c => c.id === id ? { ...c, ...patch } : c)), [setConversations]);

  const deleteConv = (id: string) => {
    const rest = conversations.filter(c => c.id !== id);
    if (rest.length === 0) {
      const c = newConv();
      setConversations([c]);
      setActiveConvId(c.id);
      return;
    }
    setConversations(rest);
    if (id === activeConvId) setActiveConvId(rest[0].id);
  };

  const selectProject = (p: Project) => {
    setActiveProjectId(p.id);
    setProjectDir(projectFolders(p)[0] ?? "");
  };

  const [creatingProject, setCreatingProject] = useState(false);

  const addProject = () => {
    setOpenProjectId("");
    setView("projects");
    setCreatingProject(true);
  };

  const createProject = (name: string, folders: string[]) => {
    const p: Project = { id: rid(), name, folders };
    setProjects(list => [...list, p]);
    selectProject(p);
    setOpenProjectId(p.id);
    setCreatingProject(false);
  };

  const assist = (messages: ChatMsg[], signal: AbortSignal) => streamChat({
    model: state.activeModel, messages, numCtx: state.contextLength, temperature: 0.4, top_p: 0.9, signal,
    ...approvedTune(state, state.activeModel),
  });

  const updateProject = (id: string, patch: Partial<Project>) => {
    setProjects(list => list.map(p => p.id === id ? { ...p, ...patch } : p));
    if (("folders" in patch || "dir" in patch) && id === activeProjectId) setProjectDir(patch.folders?.[0] ?? "");
  };

  const removeProject = (id: string) => {
    setProjects(list => list.filter(p => p.id !== id));
    setConversations(list => list.map(c => c.projectId === id ? { ...c, projectId: undefined } : c));
    if (activeProjectId === id) setActiveProjectId("");
  };

  const switchMode = (m: Mode) => {
    setMode(m);
    setView("chat");
    const want = (c: Conversation) => (m === "agents" ? !!c.agentId : !c.agentId);
    const current = conversations.find(c => c.id === activeConvId);
    if (current && want(current)) return;
    const next = conversations.find(want);
    if (next) setActiveConvId(next.id);
    else if (m === "chat") createConv();
  };

  const openAgent = (a: Agent) => {
    const existing = conversations.find(c => c.agentId === a.id);
    if (existing) { setActiveConvId(existing.id); setView("chat"); }
    else createConv({ agentId: a.id });
  };

  const selectConv = (id: string) => {
    const c = conversations.find(x => x.id === id);
    setActiveConvId(id);
    setView("chat");
    const pr = projects.find(p => p.id === c?.projectId);
    if (pr) selectProject(pr);
  };

  const stateRef = useRef(state);
  stateRef.current = state;
  const jobsRef = useRef(jobs);
  jobsRef.current = jobs;
  const runningJobs = useRef(new Set<string>());

  const runJob = useCallback(async (id: string) => {
    const job = jobsRef.current.find(j => j.id === id);
    const st = stateRef.current;
    if (!job || runningJobs.current.has(id) || !st.connected || !st.activeModel) return;
    runningJobs.current.add(id);
    setJobs(list => list.map(j => j.id === id ? { ...j, lastRun: Date.now() } : j));
    const taskId = taskApi.start(`job: ${job.name}`);
    const ep = EFFORT_PARAMS[st.effort];
    let text = "";
    let failed = false;
    try {
      for await (const piece of streamChat({
        model: st.activeModel, messages: [{ role: "user", content: job.prompt }],
        numCtx: st.contextLength, ...approvedTune(st, st.activeModel), temperature: ep.temperature, top_p: ep.top_p,
      })) text += piece;
    } catch (err) {
      failed = true;
      text += `${text ? "\n" : ""}[error] ${String(err)}`;
    } finally {
      runningJobs.current.delete(id);
      taskApi.finish(taskId, failed ? "error" : "done");
      setInbox(list => [{ id: rid(), title: job.name, text, ts: Date.now(), read: false }, ...list].slice(0, 200));
    }
  }, [taskApi, setJobs, setInbox]);

  useEffect(() => {
    const t = setInterval(() => {
      const now = Date.now();
      for (const j of jobsRef.current) {
        if (j.enabled && now - (j.lastRun ?? j.createdAt) >= j.everyMin * 60_000) void runJob(j.id);
      }
    }, JOB_TICK_MS);
    return () => clearInterval(t);
  }, [runJob]);

  const activeConv = conversations.find(c => c.id === activeConvId) ?? conversations[0];
  const activeProject = projects.find(p => p.id === activeConv.projectId);
  const activeAgent = state.agents.find(a => a.id === (activeConv.agentId ?? activeProject?.agentId));
  const title = view === "chat"
    ? (activeAgent ? `${activeAgent.name} - ${activeConv.title}` : activeConv.title)
    : VIEW_TITLES[view];

  const page = (() => {
    switch (view) {
      case "projects":
        return <ProjectsPage projects={projects} conversations={conversations} agents={state.agents} activeProjectId={activeProjectId}
          openId={openProjectId} onOpenId={id => { setOpenProjectId(id); const pr = projects.find(x => x.id === id); if (pr) selectProject(pr); }}
          creating={creatingProject} onCloseCreate={() => setCreatingProject(false)} onStartCreate={() => setCreatingProject(true)} onCreate={createProject} onUpdate={updateProject} assist={assist} onOpenConv={selectConv}
          onNewSession={id => createConv({ projectId: id })} onRemove={removeProject} />;
      case "capabilities":
        return <CapabilitiesPage models={state.models} connected={state.connected} engine={state.engine} runtime={state.runtime} onRetry={() => { void retryRuntime().then(poll); }} />;
      case "messaging":
        return <MessagingPage items={inbox} onDelete={id => setInbox(l => l.filter(i => i.id !== id))} onClear={() => setInbox([])} />;
      case "artifacts":
        return <ArtifactsPage conversations={conversations} />;
      case "jobs":
        return <JobsPage jobs={jobs} onChange={setJobs} onRunNow={id => void runJob(id)} />;
      default:
        return null;
    }
  })();

  return (
    <div style={{ display: "flex", width: "100%", height: "100%", overflow: "hidden" }}>
      {layout.leftOpen && (
        <Sidebar
          mode={mode}
          onModeChange={switchMode}
          view={view}
          onView={setView}
          conversations={conversations}
          activeConvId={activeConvId}
          onSelectConv={selectConv}
          onNewConv={projectId => createConv({ projectId })}
          onTogglePin={id => updateConv(id, { pinned: !conversations.find(c => c.id === id)?.pinned })}
          onDeleteConv={deleteConv}
          projects={projects}
          activeProjectId={activeProjectId}
          onSelectProject={p => { selectProject(p); setOpenProjectId(p.id); setView("projects"); }}
          onAddProject={addProject}
          agents={state.agents}
          activeAgentId={activeConv.agentId}
          onOpenAgent={openAgent}
          onRefreshAgents={poll}
          unread={inbox.filter(i => !i.read).length}
          connected={state.connected}
          engine={state.engine}
          accelerated={state.accelerated}
          tps={state.tps}
        />
      )}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
        <TopBar
          title={title}
          connected={state.connected}
          tps={state.tps}
          leftOpen={layout.leftOpen}
          onToggleLeft={() => setLayout(l => ({ ...l, leftOpen: !l.leftOpen }))}
          openPanels={layout.panels}
          onTogglePanel={togglePanel}
        />
        {view === "chat" ? (
          <ChatView
            key={activeConv.id}
            conv={activeConv}
            agent={activeAgent}
            project={activeProject}
            state={state}
            onConvUpdate={updateConv}
            onModelChange={m => setState(s => ({ ...s, activeModel: m }))}
            onContextChange={(n, t) => setState(s => {
              const tune = { ...s.tune };
              if (t) tune[s.activeModel] = t; else delete tune[s.activeModel];
              return { ...s, contextLength: n, tune };
            })}
            onEffortChange={e => setState(s => ({ ...s, effort: e }))}
            onTps={t => setState(s => ({ ...s, tps: t }))}
            taskApi={taskApi}
          />
        ) : page}
      </div>
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
