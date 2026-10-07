import { useCallback, useEffect, useRef, useState } from "react";
import type { Safety, Agent, Group, Project, Attachment, AppState, Conversation, Effort, Message, TaskApi, Tune } from "../types";
import { EFFORT_PARAMS } from "../types";
import { streamChat, approvedTune, loadTools, runTool } from "../api";
import type { ChatMsg, ModelState, ToolCall, ToolInfo, ToolResult } from "../api";
import { TOOL_GROUPS, activeTools, extractPaths, matchGroups } from "../toolRouting";
import { projectContext, projectFolders, rid, splitThink } from "../util";
import MessageList from "./MessageList";
import ApprovalCard from "./ApprovalCard";
import type { Choice } from "./ApprovalCard";
import { approvals } from "../approvals";
import InputArea from "./InputArea";

interface Props {
  conv: Conversation;
  agent?: Agent;
  group?: Group;
  project?: Project;
  projects: Project[];
  state: AppState;
  onConvUpdate: (id: string, patch: Partial<Conversation>) => void;
  onModelChange: (m: string) => void;
  onContextChange: (n: number, tune?: Tune) => void;
  onEffortChange: (e: Effort) => void;
  onSafetyChange: (s: Safety) => void;
  onManageModels: () => void;
  modelState: ModelState | null;
  onTps: (t: number) => void;
  taskApi: TaskApi;
}

interface Queued { text: string; atts: Attachment[]; truncateAt?: string }   // truncateAt: id of an edited message; everything from it on is replaced

const HISTORY_LIMIT = 40;
const MAX_ROUNDS = 16;
const NO_MORE_TOOLS = "(Tool limit reached. Do not call any more tools. Answer now with what you found so far, and say what is still unknown.)";
const groupHint = (g: Group | undefined, agents: Agent[]) => {
  if (!g) return "";
  const names = g.members.map(id => agents.find(a => a.id === id)?.name).filter(Boolean).join(", ");
  return `You lead the group "${g.name}". Your team: ${names || "(no members yet)"}. Split the user's request into sub-tasks, ask the right members with ask_agent (give each all the context it needs), then combine their answers into one reply for the user. Do simple things yourself.`;
};

const TOOLS_HINT = "You can use tools, but only some are active for each message. If you need a kind of tool you do not have (Files, Web, Shell, Skills, Memory, Agents, Git or Utilities), call use_tools to switch it on. " +
  "Use tools when they help, and never claim you did something you did not do with a tool. " +
  "Read a file before editing it. Relative file paths start in the first folder listed by workspace_folders. For multi-step work keep a short plan with update_plan. " +
  "Use ask_user when something essential is missing. Use remember only for lasting facts, never secrets. " +
  "To find something on the user's computer use search_computer, then read_file; to find a folder or file by name use search_computer (it finds folders too); to understand a folder call analyze_folder ONCE (never walk it folder by folder). Folders outside the project ask the user for approval automatically. " +
  "Do not repeat a call you already made. Stop calling tools as soon as you have enough to answer.";

/** Tools that are confirmed every single time, whatever the safety mode or earlier approvals. */
const ALWAYS_ASK = new Set(["git_push"]);

const allowedBySafety = (t: ToolInfo, safety: Safety) =>
  safety === "off" ? false : safety === "plan" ? ["read", "net", "memory", "ui"].includes(t.kind) : true;

const toolLabel = (name: string, args: Record<string, unknown>) => {
  const first = Object.values(args).find(v => typeof v === "string") as string | undefined;
  return first ? `${name}  ${first.replace(/\s+/g, " ").slice(0, 70)}` : name;
};

/** update_plan: replace the Plan panel's steps (the panel listens for this event). */
function updatePlan(steps: unknown): { ok: boolean; result: string } {
  if (!Array.isArray(steps)) return { ok: false, result: "steps must be a list" };
  const items = steps.map((s: { text?: string; status?: string }, i) => ({
    id: `${Date.now()}-${i}`, text: String(s.text ?? ""), done: s.status === "done", doing: s.status === "doing",
  })).filter(i => i.text);
  try { localStorage.setItem("herama.plan", JSON.stringify(items)); } catch { /* storage unavailable */ }
  window.dispatchEvent(new Event("herama:plan"));
  return { ok: true, result: `Plan updated (${items.length} steps).` };
}
const b64 = (dataUrl: string) => dataUrl.slice(dataUrl.indexOf(",") + 1);

/** Drop the oldest messages until the conversation fits ~75% of the context (rough 2.5 chars per token). */
function fitToContext(msgs: Message[], ctx: number, reserved = 0): Message[] {
  const budget = Math.max(1000, ctx * 0.75 * 2.5 - reserved);
  let used = 0;
  const kept: Message[] = [];
  for (let i = msgs.length - 1; i >= 0; i--) {
    const m = msgs[i];
    const len = (m.role === "assistant" ? splitThink(m.content).answer : m.content).length + (m.images?.length ?? 0) * 2000;
    if (kept.length && used + len > budget) break;  // always keep the newest message
    used += len;
    kept.unshift(m);
  }
  return kept;
}

/** Ask the model to fold older messages into a short running summary (so long chats keep their thread without filling the context). */
async function summarize(prev: string | undefined, old: Message[], model: string, numCtx: number): Promise<string> {
  const lines = old.map(m => `[${m.role}] ${(m.role === "assistant" ? splitThink(m.content).answer : m.content).slice(0, 1200)}`).join("\n");
  const prompt = `${prev ? `Summary so far:\n${prev}\n\n` : ""}New messages:\n${lines.slice(-14000)}\n\n` +
    "Write the updated summary in at most 250 words, in the language of the conversation. Keep decisions, facts about the user, names, file paths and open tasks. Plain text only.";
  let out = "";
  for await (const piece of streamChat({
    model, numCtx, temperature: 0.2, top_p: 0.8, tools: [],
    messages: [{ role: "system", content: "You compress conversations into short, faithful summaries." }, { role: "user", content: prompt }],
  })) out += piece;
  return splitThink(out).answer.trim();
}

const PLAN_HINT = "Plan mode: you may only read, search and look things up. For anything that changes files or runs commands, describe a short numbered plan and do not claim to have changed anything.";

export default function ChatView({ conv, agent, group, project, projects, state, onConvUpdate, onModelChange, onContextChange, onEffortChange, onSafetyChange, onManageModels, modelState, onTps, taskApi }: Props) {
  const [streaming, setStreaming] = useState(false);
  const [queue, setQueue] = useState<Queued[]>([]);
  const abortRef = useRef<AbortController | null>(null);
  // Access the user approved during this conversation: extra read-only folders, extra writable folders, whole-computer search.
  const [pending, setPending] = useState<{ title: string; detail?: string; resolve: (c: Choice) => void } | null>(null);
  const pendingRef = useRef<typeof pending>(null);
  const ask = (title: string, detail?: string) => new Promise<Choice>(resolve => {
    const p = { title, detail, resolve: (c: Choice) => { pendingRef.current = null; setPending(null); resolve(c); } };
    pendingRef.current = p;
    setPending(p);
  });
  const grants = useRef({ read: [] as string[], write: [] as string[], computer: false });
  const model = agent?.model || state.activeModel;
  const ready = state.connected && !!model;

  const sendNow = useCallback(async ({ text, atts, truncateAt }: Queued) => {
    const ep = EFFORT_PARAMS[state.effort];
    const cid = conv.id;
    const imgs = atts.filter(a => a.kind === "image" && a.dataUrl);
    const files = atts.filter(a => a.kind === "file");
    const fileBlocks = files.map(f => `\n\n[file: ${f.name}]\n\`\`\`\n${f.text}\n\`\`\``).join("");
    const content = (text || (imgs.length ? "Describe this image." : "")) + fileBlocks;

    const userMsg: Message = {
      id: rid(), role: "user", content, ts: Date.now(),
      display: text,
      images: imgs.map(a => a.dataUrl!),
      files: files.map(f => f.name),
    };
    const asstId = rid();
    const asstTs = Date.now();
    const cut = truncateAt ? conv.messages.findIndex(m => m.id === truncateAt) : -1;
    const prior = cut >= 0 ? conv.messages.slice(0, cut) : conv.messages;
    const priorSummary = cut >= 0 ? undefined : conv.summary;
    if (cut >= 0 && conv.summary) onConvUpdate(cid, { summary: undefined });
    const base = [...prior, userMsg];
    const label = text || atts[0]?.name || "attachment";
    const title = conv.messages.length === 0 ? label.slice(0, 40) + (label.length > 40 ? "…" : "") : conv.title;

    const show = (body: string, live: boolean) =>
      onConvUpdate(cid, {
        title,
        messages: [...base, { id: asstId, role: "assistant", content: body, ts: asstTs, streaming: live }],
      });

    const dirs = projectFolders(project);
    const instrLen = (project?.instructions ?? "").length + (project?.description ?? "").length;
    const knowledge = dirs.length && window.herama?.fsKnowledge
      ? await window.herama.fsKnowledge(dirs, Math.max(0, Math.floor(state.contextLength * 0.4 * 2.5) - instrLen)).catch(() => undefined)
      : undefined;
    const baseSystem = [agent?.system_prompt, groupHint(group, state.agents), state.safety === "plan" ? PLAN_HINT : "", projectContext(project, knowledge)].filter(Boolean).join("\n\n");
    const convo = base.filter(m => m.role !== "tool");
    let fitted = fitToContext(convo.slice(-HISTORY_LIMIT), state.contextLength, baseSystem.length);
    let summary = priorSummary?.text ?? "";
    if (fitted.length < convo.length) {   // older messages no longer fit: keep their gist in a running summary
      fitted = fitToContext(convo.slice(-HISTORY_LIMIT), state.contextLength, baseSystem.length + 2500);
      const dropped = convo.slice(0, convo.length - fitted.length);
      const from = priorSummary ? dropped.findIndex(m => m.id === priorSummary.upTo) + 1 : 0;
      const fresh = dropped.slice(from);
      if (fresh.length >= 2) {
        show("", true);
        setStreaming(true);
        try {
          const text2 = await summarize(priorSummary?.text, fresh, model, state.contextLength);
          if (text2) { summary = text2; onConvUpdate(cid, { summary: { text: text2, upTo: dropped[dropped.length - 1].id } }); }
        } catch { /* keep the old summary; the oldest messages are simply dropped */ }
      }
    } else summary = "";
    const system = [baseSystem, summary ? `Summary of the earlier part of this conversation:\n${summary}` : ""].filter(Boolean).join("\n\n");
    const history: ChatMsg[] = fitted
      .map(m => ({ role: m.role as "user" | "assistant", content: m.role === "assistant" ? splitThink(m.content).answer : m.content }));
    if (imgs.length) history[history.length - 1].images = imgs.map(a => b64(a.dataUrl!));
    const messages: ChatMsg[] = system
      ? [{ role: "system", content: system }, ...history]
      : history;

    const ctrl = new AbortController();
    abortRef.current = ctrl;
    const turn: Message[] = [{ id: asstId, role: "assistant", content: "", ts: asstTs, streaming: true }];
    const render = () => onConvUpdate(cid, { title, messages: [...base, ...turn] });
    const patchLast = (patch: Partial<Message>) => { turn[turn.length - 1] = { ...turn[turn.length - 1], ...patch }; render(); };
    const patchAt = (i: number, patch: Partial<Message>) => { turn[i] = { ...turn[i], ...patch }; render(); };
    render();
    setStreaming(true);
    const taskId = taskApi.start(`chat: ${label.slice(0, 40)}`);
    let failed = false;
    let tokens = 0;
    let tFirst = 0;

    const all = await loadTools();
    // Tool groups switch on from keywords in the message (and the groups the previous turn used), so the model never sees every tool at once.
    const lastUser = conv.messages.map(m => m.role).lastIndexOf("user");
    const inherited = conv.messages.slice(Math.max(0, lastUser)).filter(m => m.role === "tool")
      .map(m => all.find(t => t.name === (m.toolLabel ?? "").split(/\s/)[0])?.group).filter((g): g is string => !!g);
    const active = new Set<string>([...matchGroups(text), ...inherited, ...(group ? ["Agents"] : [])]);
    const mentioned = extractPaths(text);   // paths the user wrote are theirs to share: read access without asking
    const saved = (p: string) => approvals.keys(p).map(k => k.slice(p.length));
    grants.current.read = [...new Set([...grants.current.read, ...saved("read:"), ...mentioned])];
    grants.current.write = [...new Set([...grants.current.write, ...saved("write:")])];
    grants.current.computer = grants.current.computer || approvals.has("computer");
    const pick = () => activeTools(all, active).filter(t => allowedBySafety(t, state.safety));
    if (all.some(t => allowedBySafety(t, state.safety))) {
      if (messages[0]?.role === "system") messages[0] = { ...messages[0], content: `${messages[0].content}\n\n${TOOLS_HINT}` };
      else messages.unshift({ role: "system", content: TOOLS_HINT });
      if (mentioned.length) messages[0] = { ...messages[0], content: `${messages[0].content}\n\nThe user gave these paths (you can read them): ${mentioned.join("; ")}` };
    }

    const execWithAccess = async (name: string, args: Record<string, unknown>): Promise<ToolResult> => {
      const go = () => runTool(name, args, [...dirs, ...grants.current.write], grants.current.read, grants.current.computer, agent?.id ?? "default", model, group?.id ?? "");
      const res = await go();
      const na = res.needs_access;
      if (!na) return res;
      const what = na.folder === "*computer*" ? "search the files on your computer" : na.write ? `change files in ${na.folder}` : `read files in ${na.folder}`;
      // Auto mode shares read access freely; changing files outside the project is always confirmed.
      const key = na.folder === "*computer*" ? "computer" : `${na.write ? "write" : "read"}:${na.folder}`;
      if (!(state.safety === "auto" && !na.write)) {
        const c = await ask(`Allow the agent to ${what}?`, na.folder === "*computer*" ? undefined : na.folder);
        if (c === "cancel") return { ok: false, result: `The user did not allow the agent to ${what}.` };
        if (c !== "once") approvals.remember(key, c);
      }
      if (na.folder === "*computer*") grants.current.computer = true;
      else (na.write ? grants.current.write : grants.current.read).push(na.folder);
      return go();
    };

    const seen = new Map<string, number>();   // identical calls made this turn
    let stuck = false;

    try {
      for (let round = 0; round < MAX_ROUNDS; round++) {
        let text = "";
        let calls: ToolCall[] = [];
        const finalRound = round === MAX_ROUNDS - 1 || stuck;   // out of steps or going in circles: answer without tools
        if (finalRound) messages.push({ role: "user", content: NO_MORE_TOOLS });
        for await (const piece of streamChat({
          model, messages, numCtx: state.contextLength, ...approvedTune(state, model), temperature: ep.temperature, top_p: ep.top_p,
          signal: ctrl.signal, agent: agent?.id ?? "default", tools: finalRound ? [] : pick().map(t => t.schema), onToolCalls: c => { calls = c; },
        })) {
          text += piece;
          if (!tFirst) tFirst = performance.now();
          else {
            tokens++;
            const elapsed = (performance.now() - tFirst) / 1000;
            if (elapsed > 0.5) onTps(tokens / elapsed);
          }
          patchLast({ content: text, streaming: true });
        }
        if (calls.length === 0) break;

        patchLast({ content: text, streaming: false });
        messages.push({ role: "assistant", content: text, tool_calls: calls });
        let question = "";
        for (const call of calls) {
          if (ctrl.signal.aborted) throw new DOMException("stopped", "AbortError");
          const name = call.function.name;
          let args: Record<string, unknown> = {};
          try { args = JSON.parse(call.function.arguments || "{}") as Record<string, unknown>; } catch { /* bad JSON is reported to the model below */ }
          const info = all.find(t => t.name === name);
          turn.push({ id: rid(), role: "tool", content: "", ts: Date.now(), toolLabel: toolLabel(name, args), toolStatus: "running" });
          render();
          const row = turn.length - 1;
          let result: ToolResult;
          let declined = false;
          const sig = `${name}:${call.function.arguments}`;
          const times = (seen.get(sig) ?? 0) + 1;
          seen.set(sig, times);
          const always = ALWAYS_ASK.has(name);
          if (info && times === 1 && (always || (state.safety === "ask" && (info.kind === "write" || info.kind === "exec") && !approvals.has(`tool:${name}`)))) {
            const c = await ask(always ? "Push to the remote repository? (asked every time)" : `Allow the agent to run ${name}?`, JSON.stringify(args, null, 2).slice(0, 1200));
            if (c === "cancel") declined = true;
            else if (c !== "once" && !always) approvals.remember(`tool:${name}`, c);
          }
          if (times > 1 && info?.kind !== "ui") {
            if (times >= 3) stuck = true;
            result = { ok: false, result: "You already made this exact call. Use the earlier result and continue, or answer now." };
          } else if (!info) result = { ok: false, result: `unknown tool: ${name}` };
          else if (declined) {
            result = { ok: false, result: "The user declined this action." };
          } else if (name === "ask_user") {
            question = String(args.question ?? "");
            result = { ok: true, result: "Question shown to the user." };
          } else if (name === "use_tools") {
            const asked = (Array.isArray(args.groups) ? args.groups : []).map(String).filter(g => (TOOL_GROUPS as readonly string[]).includes(g));
            asked.forEach(g => active.add(g));
            const names = all.filter(t => asked.includes(t.group) && allowedBySafety(t, state.safety)).map(t => t.name);
            result = asked.length ? { ok: true, result: `Switched on: ${asked.join(", ")}. Tools now available: ${names.join(", ") || "none in this mode"}.` }
              : { ok: false, result: `Unknown group. Choose from: ${TOOL_GROUPS.join(", ")}.` };
          } else if (name === "update_plan") {
            result = updatePlan(args.steps);
          } else {
            result = await execWithAccess(name, args);
          }
          patchAt(row, { toolStatus: result.ok ? "done" : "error", content: result.result });
          messages.push({ role: "tool", tool_call_id: call.id, content: result.result });
        }
        if (question) { turn.push({ id: rid(), role: "assistant", content: question, ts: Date.now() }); render(); break; }
        turn.push({ id: rid(), role: "assistant", content: "", ts: Date.now(), streaming: true });
        render();
      }
    } catch (err) {
      if (!(err instanceof DOMException && err.name === "AbortError")) {
        failed = true;
        patchLast({ content: `${turn[turn.length - 1].content}${turn[turn.length - 1].content ? "\n" : ""}[error] ${String(err)}` });
      }
    } finally {
      const stopped = ctrl.signal.aborted;
      const last = turn[turn.length - 1];
      if (last.role === "assistant" && !last.content) {
        if (turn.length > 1 && !stopped) turn.pop();  // nothing more to say after the tool results
        else if (stopped) patchLast({ content: "[stopped]" });
        else { failed = true; patchLast({ content: "[error] the model returned an empty response" }); }
      }
      for (let i = 0; i < turn.length; i++) {
        if (turn[i].streaming || turn[i].toolStatus === "running") turn[i] = { ...turn[i], streaming: false, toolStatus: turn[i].toolStatus === "running" ? "error" : turn[i].toolStatus };
      }
      abortRef.current = null;
      taskApi.finish(taskId, failed ? "error" : "done");
      render();
      setStreaming(false);
    }
  }, [model, state.effort, state.safety, state.contextLength, state.tune, conv, agent, project, onConvUpdate, onTps, taskApi]);

  const [draft, setDraft] = useState<{ text: string; n: number }>();
  const msgActions = {
    canEdit: !streaming && ready,
    onReply: (t: string) => setDraft({ text: t, n: Date.now() }),
    onEdit: (id: string, t: string) => { if (!streaming) void sendNow({ text: t, atts: [], truncateAt: id }); },
    onReact: (id: string, emoji: string | undefined) => !streaming && onConvUpdate(conv.id, { messages: conv.messages.map(m => m.id === id ? { ...m, reaction: emoji } : m) }),
  };

  const submit = (text: string, atts: Attachment[]) => {
    if (streaming) setQueue(q => [...q, { text, atts }]);
    else void sendNow({ text, atts });
  };

  useEffect(() => {
    if (streaming || queue.length === 0 || !ready) return;
    const [next, ...rest] = queue;
    setQueue(rest);
    void sendNow(next);
  }, [streaming, queue, ready, sendNow]);

  const stop = () => {
    pendingRef.current?.resolve("cancel");
    setQueue([]);
    abortRef.current?.abort();
  };

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", background: "var(--bg)", minHeight: 0 }}>
      <MessageList messages={conv.messages} actions={msgActions} footer={pending ? <ApprovalCard title={pending.title} detail={pending.detail} onChoose={pending.resolve} /> : null} />
      <InputArea
        draft={draft}
        models={state.models}
        activeModel={model}
        effort={state.effort}
        contextLength={state.contextLength}
        tps={state.tps}
        streaming={streaming}
        queue={queue.map(q => q.text || q.atts[0]?.name || "attachment")}
        onRemoveQueued={i => setQueue(q => q.filter((_, j) => j !== i))}
        onSend={submit}
        onStop={stop}
        onModelChange={onModelChange}
        onEffortChange={onEffortChange}
        onManageModels={onManageModels}
        modelState={modelState}
        safety={state.safety}
        onSafetyChange={onSafetyChange}
        projects={projects}
        projectId={conv.projectId}
        onProject={id => onConvUpdate(conv.id, { projectId: id || undefined })}
        agents={state.agents}
        agentName={agent?.name}
        onAgent={id => onConvUpdate(conv.id, { agentId: id || undefined })}
        onContextChange={onContextChange}
        disabled={!ready}
        placeholder={!state.connected ? "backend offline" : !model ? "no model found - put a .gguf file in the models folder" : agent ? `message ${agent.name}...` : streaming ? "type to queue the next message..." : "message herama..."}
      />
    </div>
  );
}
