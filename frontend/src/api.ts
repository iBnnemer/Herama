import type { Agent } from "./types";

export const BASE = "http://127.0.0.1:11434";

export interface RuntimeInfo { state: string; backend: string; progress: number; error: string }
export interface Health { engine?: string; accelerated?: boolean | null; runtime?: RuntimeInfo }

export async function retryRuntime(): Promise<void> {
  try { await fetch(`${BASE}/api/runtime/retry`, { method: "POST" }); } catch { /* backend offline */ }
}

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

export interface HubHardware { cpu: string; cpu_cores: number; gpu: string; vram_total_gb: number; vram_free_gb: number; ram_total_gb: number; ram_free_gb: number }
export interface HubRepo { id: string; downloads: number; likes: number }
export interface HubFile { file: string; size: number; quant: string; moe: boolean; active_ratio: number; fit: "gpu" | "split" | "cpu" | "too_big"; tps: number; vram_gb: number; ram_gb: number }
export interface HubJob { id: string; repo: string; file: string; name: string; state: string; done: number; total: number; speed: number; error: string }

async function hubJson<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${BASE}/api/hub${path}`, init);
  if (!r.ok) {
    const d = await r.json().catch(() => ({}));
    throw new Error(d.detail ?? `request failed (${r.status})`);
  }
  return r.json() as Promise<T>;
}

export const hubSearch = (q: string, moe = false, uncensored = false) =>
  hubJson<HubRepo[]>(`/search?q=${encodeURIComponent(q)}&moe=${moe}&uncensored=${uncensored}`);
export const hubFiles = (repo: string) => hubJson<{ hardware: HubHardware; files: HubFile[] }>(`/files?repo=${encodeURIComponent(repo)}`);
export const hubHardware = () => hubJson<HubHardware>("/hardware");
export const hubDownloads = () => hubJson<HubJob[]>("/downloads");
export const hubDownload = (repo: string, file: string, size: number) =>
  hubJson<HubJob>("/download", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ repo, file, size }) });
export const hubCancel = (id: string) => hubJson<{ ok: boolean }>(`/downloads/${id}`, { method: "DELETE" });
