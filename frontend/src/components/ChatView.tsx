import { useCallback, useState } from "react";
import type { AppState, Conversation, Effort, Message } from "../types";
import { EFFORT_PARAMS } from "../types";
import { streamGenerate } from "../api";
import MessageList from "./MessageList";
import InputArea from "./InputArea";

interface Props {
  conv: Conversation;
  state: AppState;
  onConvUpdate: (p: Partial<Conversation>) => void;
  onNewConv: (agentId?: string) => void;
  onModelChange: (m: string) => void;
  onContextChange: (n: number) => void;
  onEffortChange: (e: Effort) => void;
  onTps: (t: number) => void;
}

let _id = 0;
const uid = () => String(++_id);

export default function ChatView({ conv, state, onConvUpdate, onModelChange, onContextChange, onEffortChange, onTps }: Props) {
  const [streaming, setStreaming] = useState(false);

  const send = useCallback(async (text: string) => {
    if (streaming || !state.activeModel) return;
    const ep = EFFORT_PARAMS[state.effort];

    const userMsg: Message = { id: uid(), role: "user", content: text, ts: Date.now() };
    const asstId = uid();
    const asstMsg: Message = { id: asstId, role: "assistant", content: "", ts: Date.now(), streaming: true };

    const title = conv.messages.length === 0
      ? text.slice(0, 40) + (text.length > 40 ? "…" : "")
      : conv.title;

    onConvUpdate({ messages: [...conv.messages, userMsg, asstMsg], title });
    setStreaming(true);

    const t0 = performance.now();
    let tokens = 0;
    let full = "";

    try {
      for await (const { token } of streamGenerate({
        model: state.activeModel,
        prompt: text,
        system: undefined,
        numCtx: state.contextLength,
        temperature: ep.temperature,
        top_p: ep.top_p,
      })) {
        full += token;
        tokens++;
        const elapsed = (performance.now() - t0) / 1000;
        if (elapsed > 0.5) onTps(tokens / elapsed);
        onConvUpdate({
          messages: [
            ...conv.messages, userMsg,
            { id: asstId, role: "assistant", content: full, ts: asstMsg.ts, streaming: true },
          ],
        });
      }
    } finally {
      onConvUpdate({
        messages: [
          ...conv.messages, userMsg,
          { id: asstId, role: "assistant", content: full, ts: asstMsg.ts, streaming: false },
        ],
      });
      setStreaming(false);
    }
  }, [streaming, state, conv, onConvUpdate, onTps]);

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", background: "var(--bg)" }}>
      {/* Top bar */}
      <div className="titlebar" style={{
        height: 44, display: "flex", alignItems: "center", padding: "0 20px",
        borderBottom: "1px solid var(--border)", flexShrink: 0, gap: 10,
      }}>
        <span style={{ fontSize: 13, color: "var(--text-mid)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {conv.title}
        </span>
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: "var(--text-dim)" }}>
          {state.tps > 0 && <span>{state.tps.toFixed(1)} t/s</span>}
          <span style={{
            width: 7, height: 7, borderRadius: "50%", flexShrink: 0,
            background: state.connected ? "var(--green)" : "var(--border2)",
          }} />
        </div>
      </div>

      {/* Messages */}
      <MessageList messages={conv.messages} />

      {/* Input */}
      <InputArea
        models={state.models}
        activeModel={state.activeModel}
        effort={state.effort}
        contextLength={state.contextLength}
        tps={state.tps}
        onSend={send}
        onModelChange={onModelChange}
        onEffortChange={onEffortChange}
        onContextChange={onContextChange}
        disabled={streaming || !state.connected || !state.activeModel}
        placeholder={!state.activeModel ? "no model loaded — start backend first" : "message herama…"}
      />
    </div>
  );
}
