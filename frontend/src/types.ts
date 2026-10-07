export type Mode = "chat" | "agents";

export type Safety = "ask" | "plan" | "auto" | "off";

export type Effort = "low" | "medium" | "high" | "max";

export const EFFORT_LEVELS: Effort[] = ["low", "medium", "high", "max"];

export interface Message {
  id: string;
  role: "user" | "assistant" | "tool";
  content: string;
  ts: number;
  streaming?: boolean;
  display?: string;
  images?: string[];
  files?: string[];
  toolLabel?: string;
  toolStatus?: "running" | "done" | "error";
}

export interface Conversation {
  id: string;
  title: string;
  messages: Message[];
  agentId?: string;   // for a group chat this is the lead
  groupId?: string;
  projectId?: string;
  pinned?: boolean;
}

export type View = "chat" | "projects" | "capabilities" | "messaging" | "artifacts" | "jobs";

/** A project works like a Claude project: instructions, knowledge files, a managing agent and its own sessions. */
export interface Project {
  id: string;
  name: string;
  description?: string;
  instructions?: string;
  folders?: string[]; // knowledge folders: their file tree and text files are given to every session
  agentId?: string;   // agent that manages the project; its sessions use this agent by default
  dir?: string;       // legacy single folder, migrated into folders
}

export interface Job {
  id: string;
  name: string;
  prompt: string;
  everyMin: number;
  enabled: boolean;
  createdAt: number;
  lastRun?: number;
}

export interface InboxItem { id: string; title: string; text: string; ts: number; read: boolean }

export interface Agent {
  id: string;
  name: string;
  model: string;
  system_prompt: string;
}

/** Agents working together: the lead receives the user's messages and delegates to the members. */
export interface Group {
  id: string;
  name: string;
  lead: string;
  members: string[];
}

export interface Model {
  name: string;
  size?: number;
}

export interface Tune { ctx: number; numGpu: number; cpuMoe: number; expertUsed: number; kvType: string; threads: number }

export interface AppState {
  connected: boolean;
  engine: string;
  accelerated: boolean | null;
  runtime: { state: string; backend: string; progress: number; error: string } | null;
  tps: number;
  models: Model[];
  agents: Agent[];
  groups: Group[];
  activeModel: string;
  contextLength: number;
  tune: Record<string, Tune>;
  effort: Effort;
  safety: Safety;
}

export const EFFORT_PARAMS: Record<Effort, { temperature: number; top_p: number; label: string; short: string }> = {
  low:    { temperature: 0.2, top_p: 0.80, label: "Low",    short: "Low"    },
  medium: { temperature: 0.5, top_p: 0.88, label: "Medium", short: "Medium" },
  high:   { temperature: 0.8, top_p: 0.93, label: "High",   short: "High"   },
  max:    { temperature: 1.1, top_p: 0.98, label: "Max",    short: "Max"    },
};

export type PanelId = "tasks" | "plan" | "browser" | "terminal" | "files";

export const PANELS: { id: PanelId; title: string }[] = [
  { id: "tasks",    title: "background tasks" },
  { id: "plan",     title: "plan" },
  { id: "browser",  title: "browser" },
  { id: "terminal", title: "terminal" },
  { id: "files",    title: "project files" },
];

export type TaskStatus = "running" | "done" | "error";

export interface Task {
  id: string;
  label: string;
  status: TaskStatus;
  ts: number;
}

export interface TaskApi {
  start: (label: string) => string;
  finish: (id: string, status: TaskStatus) => void;
}

export interface Attachment {
  id: string;
  name: string;
  kind: "image" | "file";
  dataUrl?: string;
  text?: string;
}
