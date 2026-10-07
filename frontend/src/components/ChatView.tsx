import { useCallback, useEffect, useRef, useState } from "react";
import type { Safety, Agent, Project, Attachment, AppState, Conversation, Effort, Message, TaskApi, Tune } from "../types";
import { EFFORT_PARAMS } from "../types";
import { streamChat, approvedTune } from "../api";
import type { ChatMsg } from "../api";
import { projectContext, projectFolders, rid, splitThink } from "../util";
import MessageList from "./MessageList";
import InputArea from "./InputArea";

interface Props {
  conv: Conversation;
  agent?: Agent;
  project?: Project;
  projects: Project[];
  state: AppState;
  onConvUpdate: (id: string, patch: Partial<Conversation>) => void;
  onModelChange: (m: string) => void;
  onContextChange: (n: number, tune?: Tune) => void;
  onEffortChange: (e: Effort) => void;
  onSafetyChange: (s: Safety) => void;
  onManageModels: () => void;
  onTps: (t: number) => void;
  taskApi: TaskApi;
}

interface Queued { text: string; atts: Attachment[] }

const HISTORY_LIMIT = 40;
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

const PLAN_HINT = "Plan mode: when a request needs actions on the user's machine, describe a short numbered plan and do not claim to have run anything.";

export default function ChatView({ conv, agent, project, projects, state, onConvUpdate, onModelChange, onContextChange, onEffortChange, onSafetyChange, onManageModels, onTps, taskApi }: Props) {
  const [streaming, setStreaming] = useState(false);
  const [queue, setQueue] = useState<Queued[]>([]);
  const abortRef = useRef<AbortController | null>(null);
  const model = agent?.model || state.activeModel;
  const ready = state.connected && !!model;

  const sendNow = useCallback(async ({ text, atts }: Queued) => {
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
    const base = [...conv.messages, userMsg];
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
    const system = [agent?.system_prompt, state.safety === "plan" ? PLAN_HINT : "", projectContext(project, knowledge)].filter(Boolean).join("\n\n");
    const history: ChatMsg[] = fitToContext(base
      .filter(m => m.role !== "tool")
      .slice(-HISTORY_LIMIT), state.contextLength, system.length)
      .map(m => ({ role: m.role as "user" | "assistant", content: m.role === "assistant" ? splitThink(m.content).answer : m.content }));
    if (imgs.length) history[history.length - 1].images = imgs.map(a => b64(a.dataUrl!));
    const messages: ChatMsg[] = system
      ? [{ role: "system", content: system }, ...history]
      : history;

    const ctrl = new AbortController();
    abortRef.current = ctrl;
    show("", true);
    setStreaming(true);
    const taskId = taskApi.start(`chat: ${label.slice(0, 40)}`);
    let failed = false;
    let full = "";
    let tokens = 0;
    let tFirst = 0;

    try {
      for await (const piece of streamChat({
        model, messages, numCtx: state.contextLength, ...approvedTune(state, model), temperature: ep.temperature, top_p: ep.top_p, signal: ctrl.signal,
      })) {
        full += piece;
        if (!tFirst) tFirst = performance.now();
        else {
          tokens++;
          const elapsed = (performance.now() - tFirst) / 1000;
          if (elapsed > 0.5) onTps(tokens / elapsed);
        }
        show(full, true);
      }
    } catch (err) {
      if (!(err instanceof DOMException && err.name === "AbortError")) {
        failed = true;
        full += `${full ? "\n" : ""}[error] ${String(err)}`;
      }
    } finally {
      const stopped = ctrl.signal.aborted;
      if (!full && !stopped) { failed = true; full = "[error] the model returned an empty response"; }
      if (!full && stopped) full = "[stopped]";
      abortRef.current = null;
      taskApi.finish(taskId, failed ? "error" : "done");
      show(full, false);
      setStreaming(false);
    }
  }, [model, state.effort, state.safety, state.contextLength, state.tune, conv, agent, project, onConvUpdate, onTps, taskApi]);

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
    setQueue([]);
    abortRef.current?.abort();
  };

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", background: "var(--bg)", minHeight: 0 }}>
      <MessageList messages={conv.messages} />
      <InputArea
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
