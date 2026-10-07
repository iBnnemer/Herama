import type { Agent, Group } from "./types";

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

export async function fetchGroups(): Promise<Group[]> {
  try {
    const r = await fetch(`${BASE}/api/groups`);
    return r.ok ? r.json() : [];
  } catch { return []; }
}

async function sendGroup(path: string, method: string, body?: unknown): Promise<Group> {
  const r = await fetch(`${BASE}/api/groups${path}`, { method, headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail ?? `request failed (${r.status})`);
  return r.json();
}

export const createGroup = (g: Omit<Group, "id">) => sendGroup("", "POST", g);
export const updateGroup = (id: string, g: Partial<Group>) => sendGroup(`/${id}`, "PATCH", g);
export const deleteGroup = (id: string) => sendGroup(`/${id}`, "DELETE");

export async function deleteAgent(id: string): Promise<void> {
  await fetch(`${BASE}/api/agents/${id}`, { method: "DELETE" });
}

export interface ApiProvider { id: string; label: string; provider: string; model: string; base_url: string; has_key: boolean; key_hint: string }
export interface ApiProviderIn { id?: string; label: string; provider: string; model: string; base_url: string; api_key: string }

async function providerJson<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${BASE}/api/providers${path}`, init);
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail ?? `request failed (${r.status})`);
  return r.json() as Promise<T>;
}
const post = (body: unknown): RequestInit => ({ method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export const listProviders = () => providerJson<{ presets: Record<string, string>; items: ApiProvider[] }>("");
export const saveProvider = (p: ApiProviderIn) => providerJson<ApiProvider>("", post(p));
export const testProvider = (p: ApiProviderIn) => providerJson<{ ok: boolean; detail: string }>("/test", post(p));
export const deleteProvider = (id: string) => providerJson<{ ok: boolean }>(`/${id}`, { method: "DELETE" });

export interface ToolCall { id: string; type: "function"; function: { name: string; arguments: string } }
export interface ChatMsg { role: "system" | "user" | "assistant" | "tool"; content: string; images?: string[]; tool_calls?: ToolCall[]; tool_call_id?: string }

export interface ToolInfo { name: string; group: string; kind: "read" | "net" | "memory" | "write" | "exec" | "ui"; description: string; schema: unknown; client: boolean }

let toolCache: Promise<ToolInfo[]> | null = null;
/** The built-in agent tools (loaded once). */
export function loadTools(): Promise<ToolInfo[]> {
  toolCache ??= fetch(`${BASE}/api/tools`).then(r => (r.ok ? r.json() : [])).catch(() => { toolCache = null; return []; }) as Promise<ToolInfo[]>;
  return toolCache;
}

let envCache: Promise<string> | null = null;
/** Facts about this computer (operating system, shells, tool versions) so commands are written for the versions that are really installed. */
export function loadEnvironment(): Promise<string> {
  envCache ??= fetch(`${BASE}/api/tools/environment`).then(r => (r.ok ? r.json() : { text: "" })).then(d => String(d.text ?? "")).catch(() => { envCache = null; return ""; });
  return envCache;
}

export interface ToolResult { ok: boolean; result: string; needs_access?: { folder: string; write: boolean } }

export async function runTool(name: string, args: Record<string, unknown>, dirs: string[], readDirs: string[] = [], computer = false, agent = "", model = "", group = ""): Promise<ToolResult> {
  try {
    const r = await fetch(`${BASE}/api/tools/run`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, arguments: args, dirs, read_dirs: readDirs, computer, agent, model, group }),
    });
    return r.ok ? await r.json() as ToolResult : { ok: false, result: `tool request failed (${r.status})` };
  } catch (e) {
    return { ok: false, result: String(e) };
  }
}

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
  numGpu?: number;
  cpuMoe?: number;
  expertUsed?: number;
  kvType?: string;
  threads?: number;
  temperature: number;
  top_p: number;
  signal?: AbortSignal;
  tools?: unknown[];
  agent?: string;
  onToolCalls?: (calls: ToolCall[]) => void;
}): AsyncGenerator<string> {
  const r = await fetch(`${BASE}/api/chat`, {
    method: "POST",
    signal: opts.signal,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model: opts.model,
      messages: opts.messages,
      tools: opts.tools ?? [],
      stream: true,
      memory: true,
      agent: opts.agent ?? "",
      options: { num_ctx: opts.numCtx, num_gpu: opts.numGpu, num_cpu_moe: opts.cpuMoe, num_expert_used: opts.expertUsed, kv_type: opts.kvType, num_thread: opts.threads, temperature: opts.temperature, top_p: opts.top_p },
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
        if (obj.message?.tool_calls?.length) opts.onToolCalls?.(obj.message.tool_calls as ToolCall[]);
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

export interface TunePlan {
  calibrated: "" | "measured" | "learned";
  manual: boolean; kv_type: string; adjusted: string[]; requested_ctx: number;
  layers: number; moe: boolean; experts: number; ctx: number; ctx_train: number; ngl: number; cpu_moe: number; top_k: number; default_top_k: number;
  kv_gb: number; vram_gb: number; ram_gb: number; tps: number; size_gb: number; fits: boolean;
  vram_budget_gb: number; ctx_over_training: boolean;
}

export async function fetchTune(model: string, ctx: number, ngl?: number, cpuMoe?: number, topK?: number, kv?: string): Promise<TunePlan> {
  const q = new URLSearchParams({ model, ctx: String(ctx) });
  if (ngl !== undefined) q.set("ngl", String(ngl));
  if (cpuMoe !== undefined) q.set("cpu_moe", String(cpuMoe));
  if (topK !== undefined) q.set("top_k", String(topK));
  if (kv !== undefined) q.set("kv", kv);
  const r = await fetch(`${BASE}/api/tune?${q}`);
  if (!r.ok) throw new Error(`tune failed (${r.status})`);
  return r.json() as Promise<TunePlan>;
}

/** Layout the user chose by hand for this model at the current context; automatic mode sends nothing. */
export function approvedTune(state: { contextLength: number; tune: Record<string, { ctx: number; numGpu: number; cpuMoe: number; expertUsed: number; kvType: string; threads: number }> }, model: string) {
  const t = state.tune[model];
  return t && t.ctx === state.contextLength
    ? { numGpu: t.numGpu, cpuMoe: t.cpuMoe, expertUsed: t.expertUsed, kvType: t.kvType, threads: t.threads }
    : {};
}

export type ModelStateName = "idle" | "reading" | "generating" | "queued" | "error";
export interface ModelState { state: ModelStateName; detail: string; progress: number; tps: number }
export interface MonitorRequest { time: number; status: string; prompt: number; reused: number; output: number; tps: number; hit_rate: number; duration: number }
export interface MonitorSnap {
  state: ModelState; decode_tps: number; prefill_tps: number; ctx_used: number; ctx_total: number;
  experts: { gpu_layers: number; layers: number } | null; requests: MonitorRequest[];
  gpu: { name?: string; load?: number; vram_used_mb?: number; vram_total_mb?: number; temp?: number; power?: number; power_limit?: number; pcie_gen?: number; pcie_width?: number };
  system: { cpu?: number; threads?: number; ram_used_gb?: number; ram_total_gb?: number; disk_read_mb_s?: number };
}

export async function fetchModelState(): Promise<ModelState | null> {
  try {
    const r = await fetch(`${BASE}/api/monitor/state`);
    return r.ok ? (await r.json()) as ModelState : null;
  } catch { return null; }
}

export async function fetchMonitor(): Promise<MonitorSnap | null> {
  try {
    const r = await fetch(`${BASE}/api/monitor`);
    return r.ok ? (await r.json()) as MonitorSnap : null;
  } catch { return null; }
}
