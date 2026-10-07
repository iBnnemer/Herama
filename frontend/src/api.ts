import type { Agent, Effort, EFFORT_PARAMS } from "./types";

export const BASE = "http://127.0.0.1:11434";

export async function fetchHealth(): Promise<boolean> {
  try {
    const r = await fetch(`${BASE}/health`, { signal: AbortSignal.timeout(2000) });
    return r.ok;
  } catch { return false; }
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

export async function* streamGenerate(opts: {
  model: string;
  prompt: string;
  system?: string;
  numCtx: number;
  temperature: number;
  top_p: number;
}): AsyncGenerator<{ token: string; done: boolean }> {
  const r = await fetch(`${BASE}/api/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model: opts.model,
      prompt: opts.prompt,
      system: opts.system,
      stream: true,
      options: { num_ctx: opts.numCtx, temperature: opts.temperature, top_p: opts.top_p },
    }),
  });
  if (!r.body) return;
  const reader = r.body.getReader();
  const dec = new TextDecoder();
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    for (const line of dec.decode(value).split("\n").filter(Boolean)) {
      try {
        const obj = JSON.parse(line);
        if (obj.response !== undefined) yield { token: obj.response as string, done: !!obj.done };
      } catch { /* skip */ }
    }
  }
}
