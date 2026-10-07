export type Mode = "chat" | "agents";

export interface Message {
  id: string;
  role: "user" | "assistant" | "tool";
  content: string;
  ts: number;
  streaming?: boolean;
  toolLabel?: string;
  toolStatus?: "running" | "done" | "error";
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
}
