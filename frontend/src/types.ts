export type Mode = "chat" | "agents";

export type Effort = "fast" | "balanced" | "smart";

export interface Message {
  id: string;
  role: "user" | "assistant" | "tool";
  content: string;
  ts: number;
  streaming?: boolean;
  toolLabel?: string;
  toolStatus?: "running" | "done" | "error";
}

export interface Conversation {
  id: string;
  title: string;
  messages: Message[];
  agentId?: string;
}

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

export interface AppState {
  connected: boolean;
  tps: number;
  models: Model[];
  agents: Agent[];
  activeModel: string;
  contextLength: number;
  effort: Effort;
}

export const EFFORT_PARAMS: Record<Effort, { temperature: number; top_p: number; label: string }> = {
  fast:     { temperature: 0.3, top_p: 0.85, label: "fast"     },
  balanced: { temperature: 0.7, top_p: 0.9,  label: "balanced" },
  smart:    { temperature: 1.0, top_p: 0.95, label: "smart"    },
};
