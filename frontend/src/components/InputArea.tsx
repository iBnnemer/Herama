import { useRef, useState } from "react";
import type { ClipboardEvent, DragEvent, KeyboardEvent } from "react";
import type { Attachment, Effort, Model } from "../types";
import { readAttachment } from "../util";
import EffortPicker from "./EffortPicker";
import SettingsModal from "./SettingsModal";
import Icon from "./Icons";

interface Props {
  models: Model[];
  activeModel: string;
  effort: Effort;
  contextLength: number;
  tps: number;
  streaming: boolean;
  queue: string[];
  onRemoveQueued: (i: number) => void;
  onSend: (text: string, atts: Attachment[]) => void;
  onStop: () => void;
  onModelChange: (m: string) => void;
  onEffortChange: (e: Effort) => void;
  onContextChange: (n: number) => void;
  disabled: boolean;
  placeholder?: string;
}

const shortName = (n: string) => n.replace(/:latest$/, "");

export default function InputArea(p: Props) {
  const ref = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const [showSettings, setShowSettings] = useState(false);
  const [hasText, setHasText] = useState(false);
  const [atts, setAtts] = useState<Attachment[]>([]);
  const [notice, setNotice] = useState("");

  const addFiles = async (files: File[]) => {
    for (const f of files) {
      const r = await readAttachment(f);
      if (typeof r === "string") setNotice(r);
      else { setNotice(""); setAtts(a => [...a, r]); }
    }
  };

  const send = () => {
    const text = ref.current?.value.trim() ?? "";
    if ((!text && atts.length === 0) || p.disabled) return;
    p.onSend(text, atts);
    if (ref.current) { ref.current.value = ""; ref.current.style.height = "auto"; }
    setHasText(false);
    setAtts([]);
    setNotice("");
  };

  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send(); }
    else if (e.key === "Escape" && p.streaming) p.onStop();
  };

  const onPaste = (e: ClipboardEvent<HTMLTextAreaElement>) => {
    const files = Array.from(e.clipboardData.files);
    if (files.length) { e.preventDefault(); void addFiles(files); }
  };

  const onDrop = (e: DragEvent) => {
    const files = Array.from(e.dataTransfer.files);
    if (files.length) { e.preventDefault(); void addFiles(files); }
  };

  const canSend = (hasText || atts.length > 0) && !p.disabled;
  const showStop = p.streaming && !canSend;
  const chip: React.CSSProperties = {
    background: "transparent", border: "none", borderRadius: 8, padding: "4px 8px",
    color: "var(--text-mid)", fontSize: 12, cursor: "pointer",
  };

  return (
    <div style={{ padding: "0 16px 18px", flexShrink: 0, maxWidth: 780, width: "100%", margin: "0 auto" }}>
      {p.queue.length > 0 && (
        <div style={{ marginBottom: 8, display: "flex", flexDirection: "column", gap: 4 }}>
          {p.queue.map((q, i) => (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: "var(--text-mid)", background: "var(--surface)", border: "1px dashed var(--border2)", borderRadius: 10, padding: "5px 10px" }}>
              <span style={{ color: "var(--text-dim)" }}>queued</span>
              <span dir="auto" style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{q}</span>
              <button onClick={() => p.onRemoveQueued(i)} title="remove" style={{ color: "var(--text-dim)", display: "flex" }}><Icon name="close" size={12} /></button>
            </div>
          ))}
        </div>
      )}

      <div onDragOver={e => e.preventDefault()} onDrop={onDrop} style={{
        background: "var(--surface)", border: "1px solid var(--border2)", borderRadius: 18,
        boxShadow: "0 2px 12px rgba(0,0,0,0.3)", padding: "10px 10px 8px 14px",
      }}>
        {atts.length > 0 && (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, padding: "2px 0 8px" }}>
            {atts.map(a => (
              <div key={a.id} style={{ position: "relative", border: "1px solid var(--border2)", borderRadius: 10, overflow: "hidden", background: "var(--bg2)" }}>
                {a.kind === "image"
                  ? <img src={a.dataUrl} alt={a.name} style={{ display: "block", height: 64, maxWidth: 120, objectFit: "cover" }} />
                  : <div style={{ padding: "8px 12px", fontSize: 12, color: "var(--text-mid)", maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{a.name}</div>}
                <button onClick={() => setAtts(l => l.filter(x => x.id !== a.id))} title="remove" style={{
                  position: "absolute", top: 3, right: 3, width: 18, height: 18, borderRadius: "50%",
                  background: "rgba(0,0,0,0.7)", color: "#fff", display: "flex", alignItems: "center", justifyContent: "center",
                }}><Icon name="close" size={10} /></button>
              </div>
            ))}
          </div>
        )}
        <textarea
          ref={ref}
          dir="auto"
          placeholder={p.placeholder ?? "message herama..."}
          rows={1}
          onKeyDown={onKey}
          onPaste={onPaste}
          onInput={e => {
            const t = e.currentTarget;
            t.style.height = "auto";
            t.style.height = Math.min(t.scrollHeight, 200) + "px";
            setHasText(t.value.trim().length > 0);
          }}
          style={{
            width: "100%", padding: "6px 4px", fontSize: 15, lineHeight: 1.5, minHeight: 32,
            maxHeight: 200, background: "transparent", color: "var(--text)", display: "block",
          }}
        />
        {notice && <div style={{ fontSize: 11, color: "var(--red)", padding: "2px 4px" }}>{notice}</div>}
        <div style={{ display: "flex", alignItems: "center", gap: 4, marginTop: 4 }}>
          <input ref={fileRef} type="file" multiple hidden onChange={e => { void addFiles(Array.from(e.target.files ?? [])); e.target.value = ""; }} />
          <button onClick={() => fileRef.current?.click()} title="attach files or images (or paste with Ctrl+V)"
            style={{ ...chip, display: "flex", padding: 6 }}><Icon name="clip" size={15} /></button>
          <button onClick={() => setShowSettings(true)} title="generation settings"
            style={{ ...chip, display: "flex", padding: 6 }}><Icon name="gear" size={15} /></button>

          <select
            value={p.activeModel}
            onChange={e => p.onModelChange(e.target.value)}
            style={{ ...chip, maxWidth: 240, textOverflow: "ellipsis", fontFamily: "var(--sans)" }}
          >
            {p.models.length === 0 && <option value="">no models</option>}
            {p.models.map(m => <option key={m.name} value={m.name} style={{ background: "var(--surface)" }}>{shortName(m.name)}</option>)}
          </select>

          <EffortPicker effort={p.effort} onChange={p.onEffortChange} />

          <span style={{ marginLeft: "auto", marginRight: 8, fontSize: 10, color: "var(--text-dim)" }}>
            ctx {p.contextLength >= 1024 ? `${Math.round(p.contextLength / 1024)}K` : p.contextLength}
          </span>

          <button onClick={showStop ? p.onStop : send} disabled={!showStop && !canSend}
            title={showStop ? "stop (Esc)" : p.streaming ? "add to queue" : "send"} style={{
              width: 32, height: 32, borderRadius: 10, flexShrink: 0,
              background: showStop || canSend ? "var(--accent)" : "var(--surface2)",
              color: showStop || canSend ? "#000" : "var(--text-dim)",
              display: "flex", alignItems: "center", justifyContent: "center",
            }}><Icon name={showStop ? "stop" : "send"} size={16} /></button>
        </div>
      </div>

      {showSettings && (
        <SettingsModal contextLength={p.contextLength} tps={p.tps} onApply={p.onContextChange} onClose={() => setShowSettings(false)} />
      )}
    </div>
  );
}
