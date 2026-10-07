import { useCallback, useEffect, useRef, useState } from "react";
import type { Agent, Attachment, AppState, Conversation, Effort, Message, TaskApi } from "../types";
import { EFFORT_PARAMS } from "../types";
import { streamChat } from "../api";
import type { ChatMsg } from "../api";
import { rid, splitThink } from "../util";
import MessageList from "./MessageList";
import InputArea from "./InputArea";

interface Props {
  conv: Conversation;
  agent?: Agent;
  state: AppState;
  onConvUpdate: (id: string, patch: Partial<Conversation>) => void;
  onModelChange: (m: string) => void;
  onContextChange: (n: number) => void;
  onEffortChange: (e: Effort) => void;
  onTps: (t: number) => void;
  taskApi: TaskApi;
}

interface Queued { text: string; atts: Attachment[] }

const HISTORY_LIMIT = 40;
const b64 = (dataUrl: string) => dataUrl.slice(dataUrl.indexOf(",") + 1);

export default function ChatView({ conv, agent, state, onConvUpdate, onModelChange, onContextChange, onEffortChange, onTps, taskApi }: Props) {
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

    const history: ChatMsg[] = base
      .filter(m => m.role !== "tool")
      .slice(-HISTORY_LIMIT)
      .map(m => ({ role: m.role as "user" | "assistant", content: m.role === "assistant" ? splitThink(m.content).answer : m.content }));
    if (imgs.length) history[history.length - 1].images = imgs.map(a => b64(a.dataUrl!));
    const messages: ChatMsg[] = agent?.system_prompt
      ? [{ role: "system", content: agent.system_prompt }, ...history]
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
        model, messages, numCtx: state.contextLength, temperature: ep.temperature, top_p: ep.top_p, signal: ctrl.signal,
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
  }, [model, state.effort, state.contextLength, conv, agent, onConvUpdate, onTps, taskApi]);

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
        onContextChange={onContextChange}
        disabled={!ready}
        placeholder={!state.connected ? "backend offline" : !model ? "no model found - put a .gguf file in the models folder" : agent ? `message ${agent.name}...` : streaming ? "type to queue the next message..." : "message herama..."}
      />
    </div>
  );
}
