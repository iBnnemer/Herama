export type Mode = "chat" | "agents";

export type Effort = "low" | "medium" | "high" | "xhigh" | "max";

export const EFFORT_LEVELS: Effort[] = ["low", "medium", "high", "xhigh", "max"];

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
  agentId?: string;
  projectId?: string;
  pinned?: boolean;
}

export type View = "chat" | "projects" | "capabilities" | "messaging" | "artifacts" | "jobs";

export interface Project { id: string; name: string; dir: string }

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

export interface Model {
  name: string;
  size?: number;
}

export interface Tune { ctx: number; numGpu: number; cpuMoe: number }

export interface AppState {
  connected: boolean;
  engine: string;
  accelerated: boolean | null;
  runtime: { state: string; backend: string; progress: number; error: string } | null;
  tps: number;
  models: Model[];
  agents: Agent[];
  activeModel: string;
  contextLength: number;
  tune: Record<string, Tune>;
  effort: Effort;
}

export const EFFORT_PARAMS: Record<Effort, { temperature: number; top_p: number; label: string; short: string }> = {
  low:    { temperature: 0.2, top_p: 0.80, label: "Low",        short: "Low"  },
  medium: { temperature: 0.5, top_p: 0.88, label: "Medium",     short: "Med"  },
  high:   { temperature: 0.7, top_p: 0.92, label: "High",       short: "High" },
  xhigh:  { temperature: 0.9, top_p: 0.95, label: "Extra high", short: "XHigh" },
  max:    { temperature: 1.1, top_p: 0.98, label: "Max",        short: "Max"  },
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
