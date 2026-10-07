/** Runs one scheduled job unattended: the model may search the web and read small facts, never write files or run commands. */
import { streamChat, loadTools, runTool } from "./api";
import type { ChatMsg, ToolCall } from "./api";
import { matchGroups } from "./toolRouting";

const MAX_ROUNDS = 6;
const SAFE_KINDS = ["read", "net", "memory"];

export interface JobRun {
  prompt: string;
  model: string;
  numCtx: number;
  temperature: number;
  top_p: number;
  tune?: Record<string, unknown>;
}

export async function runJobWithTools(r: JobRun): Promise<string> {
  const all = await loadTools();
  const groups = new Set<string>(matchGroups(r.prompt));
  groups.add("Web");
  const usable = all.filter(t => !t.client && SAFE_KINDS.includes(t.kind) && groups.has(t.group) && t.group !== "Schedule" && t.group !== "Agents");
  const messages: ChatMsg[] = [
    { role: "system", content: "You run unattended on a schedule. Use the web_search and open_url tools to get fresh information, then write the final answer for the user. Do not ask questions." },
    { role: "user", content: r.prompt },
  ];
  const seen = new Map<string, number>();
  let text = "";
  for (let round = 0; round < MAX_ROUNDS; round++) {
    let calls: ToolCall[] = [];
    text = "";
    const last = round === MAX_ROUNDS - 1;
    if (last) messages.push({ role: "user", content: "Write the final answer now from what you have." });
    for await (const piece of streamChat({
      model: r.model, messages, numCtx: r.numCtx, temperature: r.temperature, top_p: r.top_p, ...(r.tune ?? {}),
      tools: last ? [] : usable.map(t => t.schema), onToolCalls: c => { calls = c; },
    })) text += piece;
    if (calls.length === 0) break;
    messages.push({ role: "assistant", content: text, tool_calls: calls });
    for (const call of calls) {
      const name = call.function.name;
      let args: Record<string, unknown> = {};
      try { args = JSON.parse(call.function.arguments || "{}") as Record<string, unknown>; } catch { /* reported below */ }
      const sig = `${name}:${call.function.arguments}`;
      const n = (seen.get(sig) ?? 0) + 1;
      seen.set(sig, n);
      let out: string;
      if (!usable.some(t => t.name === name)) out = "This tool is not available in a scheduled task.";
      else if (n > 1) out = "You already made this exact call. Use the earlier result.";
      else {
        const res = await runTool(name, args, []);
        out = res.needs_access ? "Access to that folder needs the user, so it is not possible in a scheduled task." : res.result;
      }
      messages.push({ role: "tool", tool_call_id: call.id, content: out });
    }
  }
  return text;
}
