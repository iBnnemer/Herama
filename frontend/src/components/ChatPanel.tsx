import { useState, useCallback } from "react";
import type { AppState, Message } from "../types";
import { streamGenerate } from "../api";
import TopBar from "./TopBar";
import MessageList from "./MessageList";
import InputArea from "./InputArea";
import ModelBar from "./ModelBar";

interface Props {
  state: AppState;
  onModelChange: (m: string) => void;
  onContextChange: (n: number) => void;
  onTps: (t: number) => void;
}

let _id = 0;
const uid = () => String(++_id);

export default function ChatPanel({ state, onModelChange, onContextChange, onTps }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [tokenCount, setTokenCount] = useState(0);

  const send = useCallback(async (text: string) => {
    if (streaming || !state.activeModel) return;
    const userMsg: Message = { id: uid(), role: "user", content: text, ts: Date.now() };
    const asstId = uid();
    const asstMsg: Message = { id: asstId, role: "assistant", content: "", ts: Date.now(), streaming: true };

    setMessages(prev => [...prev, userMsg, asstMsg]);
    setStreaming(true);

    const t0 = performance.now();
    let tokens = 0;
    let full = "";

    try {
      for await (const chunk of streamGenerate(state.activeModel, text, undefined, state.contextLength)) {
        full += chunk;
        tokens += chunk.split(/\s+/).length;
        const elapsed = (performance.now() - t0) / 1000;
        if (elapsed > 0.5) onTps(tokens / elapsed);
        setMessages(prev => prev.map(m => m.id === asstId ? { ...m, content: full } : m));
      }
    } finally {
      setMessages(prev => prev.map(m => m.id === asstId ? { ...m, streaming: false } : m));
      setStreaming(false);
      setTokenCount(c => c + tokens);
    }
  }, [streaming, state.activeModel, state.contextLength, onTps]);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <TopBar title="chat" connected={state.connected} tps={state.tps} />
      <MessageList messages={messages} />
      <ModelBar
        models={state.models}
        activeModel={state.activeModel}
        contextLength={state.contextLength}
        tps={state.tps}
        onModelChange={onModelChange}
        onContextChange={onContextChange}
        tokenCount={tokenCount}
      />
      <InputArea
        onSend={send}
        disabled={streaming || !state.connected || !state.activeModel}
        placeholder={!state.activeModel ? "no model loaded" : "message herama…"}
      />
    </div>
  );
}
