import { useCallback, useState } from "react";
import type { Agent, AppState, Conversation, Effort, Message } from "../types";
import { EFFORT_PARAMS } from "../types";
import { streamChat } from "../api";
import type { ChatMsg } from "../api";
import { rid } from "../util";
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
  taskApi: import("../types").TaskApi;
}

const HISTORY_LIMIT = 40;

export default function ChatView({ conv, agent, state, onConvUpdate, onModelChange, onContextChange, onEffortChange, onTps, taskApi }: Props) {
  const [streaming, setStreaming] = useState(false);
  const model = agent?.model || state.activeModel;

  const send = useCallback(async (text: string) => {
    if (streaming || !model) return;
    const ep = EFFORT_PARAMS[state.effort];
    const cid = conv.id;

    const userMsg: Message = { id: rid(), role: "user", content: text, ts: Date.now() };
    const asstId = rid();
    const asstTs = Date.now();
    const base = [...conv.messages, userMsg];
    const title = conv.messages.length === 0 ? text.slice(0, 40) + (text.length > 40 ? "…" : "") : conv.title;

    const show = (content: string, live: boolean) =>
      onConvUpdate(cid, {
        title,
        messages: [...base, { id: asstId, role: "assistant", content, ts: asstTs, streaming: live }],
      });

    const history: ChatMsg[] = base
      .filter(m => m.role !== "tool")
      .slice(-HISTORY_LIMIT)
      .map(m => ({ role: m.role as "user" | "assistant", content: m.content }));
    const messages: ChatMsg[] = agent?.system_prompt
      ? [{ role: "system", content: agent.system_prompt }, ...history]
      : history;

    show("", true);
    setStreaming(true);
    const taskId = taskApi.start(`chat: ${text.slice(0, 40)}`);
    let failed = false;
    let full = "";
    let tokens = 0;
    const t0 = performance.now();

    try {
      for await (const piece of streamChat({
        model, messages, numCtx: state.contextLength, temperature: ep.temperature, top_p: ep.top_p,
      })) {
        full += piece;
        tokens++;
        const elapsed = (performance.now() - t0) / 1000;
        if (elapsed > 0.5) onTps(tokens / elapsed);
        show(full, true);
      }
    } catch (err) {
      failed = true;
      full += `${full ? "\n" : ""}[error] ${String(err)}`;
    } finally {
      taskApi.finish(taskId, failed ? "error" : "done");
      show(full, false);
      setStreaming(false);
    }
  }, [streaming, model, state.effort, state.contextLength, conv, agent, onConvUpdate, onTps, taskApi]);

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", background: "var(--bg)", minHeight: 0 }}>
      <MessageList messages={conv.messages} />
      <InputArea
        models={state.models}
        activeModel={model}
        effort={state.effort}
        contextLength={state.contextLength}
        tps={state.tps}
        onSend={send}
        onModelChange={onModelChange}
        onEffortChange={onEffortChange}
        onContextChange={onContextChange}
        disabled={streaming || !state.connected || !model}
        placeholder={!state.connected ? "backend offline" : !model ? "no model found - put a .gguf file in the models folder" : agent ? `message ${agent.name}...` : "message herama..."}
      />
    </div>
  );
}
