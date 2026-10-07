import type { Agent } from "./types";

export const BASE = "http://127.0.0.1:11434";

export interface Health { gpu_offload?: boolean; llama_cpp?: string }

export async function fetchHealth(): Promise<Health | null> {
  try {
    const r = await fetch(`${BASE}/health`, { signal: AbortSignal.timeout(2000) });
    return r.ok ? await r.json() as Health : null;
  } catch { return null; }
}

export async function fetchModels(): Promise<{ name: string }[]> {
  const r = await fetch(`${BASE}/api/tags`);
  const d = await r.json();
  return d.models ?? [];
}

export async function fetchAgents(): Promise<Agent[]> {
  try {
    const r = await fetch(`${BASE}/api/agents`);
    return r.ok ? r.json() : [];
  } catch { return []; }
}

export async function createAgent(a: Omit<Agent, "id">): Promise<Agent> {
  const r = await fetch(`${BASE}/api/agents`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(a),
  });
  return r.json();
}

export async function updateAgent(id: string, a: Partial<Agent>): Promise<Agent> {
  const r = await fetch(`${BASE}/api/agents/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(a),
  });
  return r.json();
}

export async function deleteAgent(id: string): Promise<void> {
  await fetch(`${BASE}/api/agents/${id}`, { method: "DELETE" });
}

export interface ChatMsg { role: "system" | "user" | "assistant"; content: string; images?: string[] }

export async function fetchSkills(): Promise<{ name: string; desc: string }[]> {
  try {
    const r = await fetch(`${BASE}/api/skills`);
    if (!r.ok) return [];
    const d = await r.json() as Record<string, { desc?: string }>;
    return Object.entries(d).map(([name, v]) => ({ name, desc: v.desc ?? "" }));
  } catch { return []; }
}

export async function* streamChat(opts: {
  model: string;
  messages: ChatMsg[];
  numCtx: number;
  temperature: number;
  top_p: number;
  signal?: AbortSignal;
}): AsyncGenerator<string> {
  const r = await fetch(`${BASE}/api/chat`, {
    method: "POST",
    signal: opts.signal,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model: opts.model,
      messages: opts.messages,
      stream: true,
      options: { num_ctx: opts.numCtx, temperature: opts.temperature, top_p: opts.top_p },
    }),
  });
  if (!r.ok || !r.body) throw new Error(`backend error ${r.status}: ${(await r.text()).slice(0, 200)}`);
  const reader = r.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const lines = buf.split("\n");
    buf = lines.pop() ?? "";
    for (const line of lines.filter(Boolean)) {
      try {
        const obj = JSON.parse(line);
        if (obj.error) throw new Error(String(obj.error));
        const piece = obj.message?.content;
        if (piece) yield piece as string;
      } catch (e) {
        if (e instanceof SyntaxError) continue;
        throw e;
      }
    }
  }
}
