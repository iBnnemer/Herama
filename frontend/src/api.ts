const BASE = "http://127.0.0.1:11434";

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

export async function fetchAgents(): Promise<import("./types").Agent[]> {
  const r = await fetch(`${BASE}/api/agents`);
  return r.ok ? r.json() : [];
}

export async function createAgent(a: Omit<import("./types").Agent, "id">): Promise<import("./types").Agent> {
  const r = await fetch(`${BASE}/api/agents`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(a),
  });
  return r.json();
}

export async function updateAgent(id: string, a: Partial<import("./types").Agent>): Promise<import("./types").Agent> {
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

export async function* streamGenerate(
  model: string,
  prompt: string,
  system: string | undefined,
  numCtx: number,
): AsyncGenerator<string> {
  const r = await fetch(`${BASE}/api/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model, prompt, system, stream: true, options: { num_ctx: numCtx } }),
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
        if (obj.response) yield obj.response as string;
      } catch { /* ignore */ }
    }
  }
}
