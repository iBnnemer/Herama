import { useRef, KeyboardEvent } from "react";

interface Props {
  onSend: (text: string) => void;
  disabled: boolean;
  placeholder?: string;
}

const S: Record<string, React.CSSProperties> = {
  wrap: {
    padding: "12px 16px", borderTop: "1px solid var(--border)",
    background: "var(--surface)", flexShrink: 0,
    display: "flex", alignItems: "flex-end", gap: 8,
  },
  box: {
    flex: 1, background: "var(--surface2)", border: "1px solid var(--border)",
    borderRadius: 6, padding: "8px 12px", minHeight: 40, maxHeight: 160,
    color: "var(--text)", fontSize: 13, lineHeight: 1.5, resize: "none" as const,
    overflow: "auto",
  },
  btn: {
    padding: "8px 14px", background: "var(--accent)", color: "#000",
    borderRadius: 6, fontWeight: 600, fontSize: 12, flexShrink: 0,
  },
};

export default function InputArea({ onSend, disabled, placeholder }: Props) {
  const ref = useRef<HTMLTextAreaElement>(null);

  const send = () => {
    const v = ref.current?.value.trim();
    if (!v || disabled) return;
    onSend(v);
    if (ref.current) ref.current.value = "";
  };

  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
  };

  return (
    <div style={S.wrap}>
      <textarea
        ref={ref}
        style={{ ...S.box, opacity: disabled ? 0.5 : 1 }}
        placeholder={placeholder ?? "message herama…"}
        rows={1}
        disabled={disabled}
        onKeyDown={onKey}
        onInput={e => {
          const t = e.currentTarget;
          t.style.height = "auto";
          t.style.height = Math.min(t.scrollHeight, 160) + "px";
        }}
      />
      <button style={S.btn} disabled={disabled} onClick={send}>send</button>
    </div>
  );
}
