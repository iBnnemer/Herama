import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import type {
  Mode, AppState, Agent, Group, Model, Conversation, PanelId, Task, TaskStatus, TaskApi,
  View, Project, Job, InboxItem,
} from "./types";
import { EFFORT_PARAMS } from "./types";
import type { ChatMsg, ModelState } from "./api";
import MonitorModal from "./components/MonitorModal";
import { fetchModelState, fetchHealth, fetchModels, fetchAgents, fetchGroups, streamChat, retryRuntime, approvedTune } from "./api";
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
import { runJobWithTools } from "./jobRunner";
import JobsPage from "./components/pages/JobsPage";
import Icon from "./components/Icons";
import SettingsPage from "./components/pages/SettingsPage";
import { DEFAULT_PREFS, applyScale, pruneOld } from "./prefs";
import type { Prefs } from "./prefs";

const POLL_MS = 4000;
const JOB_TICK_MS = 20_000;

const newConv = (opts: { agentId?: string; groupId?: string; projectId?: string } = {}): Conversation => ({
  id: rid(), title: "New session", messages: [], ...opts,
});

const reviveConvs = (list: Conversation[]): Conversation[] => {
  const out = list.map(c => ({ ...c, messages: c.messages.map(m => ({ ...m, streaming: false })) }));
  return out.length ? out : [newConv()];
};

interface Layout { leftOpen: boolean; panels: PanelId[]; dockWidth: number }

const VIEW_TITLES: Record<Exclude<View, "chat">, string> = {
  projects: "Projects", capabilities: "Capabilities", messaging: "Messaging",
  artifacts: "Artifacts", jobs: "Scheduled jobs"
};

const SETTINGS_KEY = "herama.settings";
type Saved = Pick<AppState, "activeModel" | "contextLength" | "tune" | "effort" | "safety">;

/** Last choices (model, context, effort, safety) from the previous run. */
function savedSettings(): Partial<Saved> {
  try {
    const v = JSON.parse(localStorage.getItem(SETTINGS_KEY) || "{}") as Partial<Saved>;
    return v && typeof v === "object" ? v : {};
  } catch { return {}; }
}

export default function App() {
  const [mode, setMode] = useState<Mode>("chat");
  const [view, setView] = useState<View>("chat");
  const [state, setState] = useState<AppState>({
    connected: false, engine: "", accelerated: null, runtime: null, tps: 0, models: [], agents: [], groups: [],
    activeModel: "", contextLength: 65536, tune: {}, effort: "medium", safety: "plan", ...savedSettings(),
  });
  useEffect(() => {
    const { activeModel, contextLength, tune, effort, safety } = state;
    try { localStorage.setItem(SETTINGS_KEY, JSON.stringify({ activeModel, contextLength, tune, effort, safety })); } catch { /* storage unavailable */ }
  }, [state.activeModel, state.contextLength, state.tune, state.effort, state.safety]); // eslint-disable-line react-hooks/exhaustive-deps
  const [conversations, setConversations] = usePersistent<Conversation[]>("herama.convs", [newConv()], reviveConvs);
  const [activeConvId, setActiveConvId] = useState<string>(() => conversations[0].id);
  useEffect(() => {  // once at startup: drop sessions older than the retention setting
    try {
      const days = (JSON.parse(localStorage.getItem("herama.prefs") || "{}") as Partial<Prefs>).retentionDays ?? 0;
      if (days > 0) setConversations(list => { const kept = pruneOld(list, days); return kept.length === list.length ? list : kept; });
    } catch { /* ignore */ }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const [layout, setLayout] = usePersistent<Layout>("herama.layout", { leftOpen: true, panels: ["tasks", "files"], dockWidth: 380 });
  const [projects, setProjects] = usePersistent<Project[]>("herama.projects", []);
  const [theme, setTheme] = usePersistent<"dark" | "light">("herama.theme", "dark");
  const [monitorOpen, setMonitorOpen] = useState(false);
  const [modelState, setModelState] = useState<ModelState | null>(null);
  useEffect(() => { document.documentElement.dataset.theme = theme; }, [theme]);
  const [prefs, setPrefs] = usePersistent<Prefs>("herama.prefs", DEFAULT_PREFS, v => ({ ...DEFAULT_PREFS, ...v }));
  useEffect(() => { applyScale(prefs.scale); }, [prefs.scale]);
  useEffect(() => {
    if (!state.connected) return;
    let live = true;
    const tick = () => { void fetchModelState().then(s => { if (live) setModelState(s); }); };
    tick();
    const t = setInterval(tick, 700);
    return () => { live = false; clearInterval(t); };
  }, [state.connected]);
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
    const [mr, ar, gr] = await Promise.allSettled([fetchModels(), fetchAgents(), fetchGroups()]);
    setState(s => {
      const models: Model[] = mr.status === "fulfilled" ? mr.value : s.models;
      const agents: Agent[] = ar.status === "fulfilled" ? ar.value : s.agents;
      const groups: Group[] = gr.status === "fulfilled" ? gr.value : s.groups;
      return { ...s, connected, engine, accelerated, runtime: health.runtime ?? null, models, agents, groups, activeModel: models.length === 0 || models.some(m => m.name === s.activeModel) ? s.activeModel : models[0].name };
    });
  }, []);

  useEffect(() => { poll(); const t = setInterval(poll, POLL_MS); return () => clearInterval(t); }, [poll]);

  const createConv = (opts: { agentId?: string; groupId?: string; projectId?: string } = {}) => {
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

  const [settingsTarget, setSettingsTarget] = useState<string | undefined>();
  const [settingsOpen, setSettingsOpen] = useState(false);
  useEffect(() => {
    if (!settingsOpen) return;
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") setSettingsOpen(false); };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [settingsOpen]);
  const [creatingProject, setCreatingProject] = useState(false);

  const addProject = () => {
    setOpenProjectId("");
    setView("projects");
    setCreatingProject(true);
  };

  const createProject = (name: string, folders: string[], r: { description?: string; instructions?: string }) => {
    const p: Project = { id: rid(), name, folders, description: r.description, instructions: r.instructions };
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
    const want = (c: Conversation) => (m === "agents" ? !!c.agentId || !!c.groupId : !c.agentId && !c.groupId);
    const current = conversations.find(c => c.id === activeConvId);
    if (current && want(current)) return;
    const next = conversations.find(want);
    if (next) setActiveConvId(next.id);
    else if (m === "chat") createConv();
  };

  const openAgent = (a: Agent) => {
    const existing = conversations.find(c => c.agentId === a.id && !c.groupId);
    if (existing) { setActiveConvId(existing.id); setView("chat"); }
    else createConv({ agentId: a.id });
  };

  const openGroup = (g: Group) => {
    const existing = conversations.find(c => c.groupId === g.id);
    if (existing) { setActiveConvId(existing.id); setView("chat"); }
    else createConv({ agentId: g.lead, groupId: g.id });
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
      text = await runJobWithTools({
        prompt: job.prompt, model: st.activeModel, numCtx: st.contextLength, tune: approvedTune(st, st.activeModel),
        temperature: ep.temperature, top_p: ep.top_p,
      });
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
  const activeGroup = state.groups.find(g => g.id === activeConv.groupId);
  const activeAgent = state.agents.find(a => a.id === (activeGroup?.lead ?? activeConv.agentId ?? activeProject?.agentId));
  const title = view === "chat"
    ? (activeGroup ? `${activeGroup.name} (group)` : activeAgent ? `${activeAgent.name} - ${activeConv.title}` : activeConv.title)
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
          onOpenSettings={() => setSettingsOpen(o => !o)}
          settingsOpen={settingsOpen}
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
          activeAgentId={activeConv.groupId ? undefined : activeConv.agentId}
          groups={state.groups}
          activeGroupId={activeConv.groupId}
          onOpenGroup={openGroup}
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
          onOpenMonitor={() => setMonitorOpen(true)}
          theme={theme}
          onToggleTheme={() => setTheme(t => t === "dark" ? "light" : "dark")}
        />
        {view === "chat" ? (
          <ChatView
            key={activeConv.id}
            conv={activeConv}
            agent={activeAgent}
            group={activeGroup}
            jobs={jobs}
            onJobsChange={setJobs}
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
            onSafetyChange={v => setState(s => ({ ...s, safety: v }))}
            projects={projects}
            modelState={modelState}
            onManageModels={() => { setSettingsTarget(`providers/local@${Date.now()}`); setSettingsOpen(true); }}
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
      {settingsOpen && (
        <div style={{ position: "fixed", inset: 0, zIndex: 60, background: "var(--bg)", display: "flex", flexDirection: "column" }}>
          <div className="titlebar" style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 16px", borderBottom: "1px solid var(--border)" }}>
            <button onClick={() => setSettingsOpen(false)} title="Close settings (Esc)" style={{ display: "flex", alignItems: "center", gap: 6, padding: "5px 10px", borderRadius: 8, border: "1px solid var(--border)", color: "var(--text-mid)", fontSize: 13 }}>
              <Icon name="back" size={14} /> Back to app
            </button>
            <span style={{ fontWeight: 600, fontSize: 15 }}>Settings</span>
          </div>
          <SettingsPage state={state} theme={theme} onTheme={setTheme} prefs={prefs} onPrefs={setPrefs} conversations={conversations}
            onClearSessions={() => { const c = newConv(); setConversations([c]); setActiveConvId(c.id); }}
            projectDir={projectDir} onProjectDir={setProjectDir}
            onModel={m => setState(s => ({ ...s, activeModel: m }))}
            onContext={n => setState(s => { const tune = { ...s.tune }; delete tune[s.activeModel]; return { ...s, contextLength: n, tune }; })}
            onEffort={e => setState(s => ({ ...s, effort: e }))} onSafety={v => setState(s => ({ ...s, safety: v }))}
            target={settingsTarget} />
        </div>
      )}
      {monitorOpen && <MonitorModal onClose={() => setMonitorOpen(false)} />}
    </div>
  );
}
