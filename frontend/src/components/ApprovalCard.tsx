export type Choice = "once" | "session" | "always" | "cancel";

interface Props { title: string; detail?: string; onChoose: (c: Choice) => void }

const btn: React.CSSProperties = {
  padding: "6px 14px", borderRadius: 8, fontSize: 12, border: "1px solid var(--border2)", background: "var(--bg2)", color: "var(--text)",
};

/** Permission request shown inside the chat: allow once, for this session, always, or cancel. */
export default function ApprovalCard({ title, detail, onChoose }: Props) {
  return (
    <div style={{ margin: "10px 0 18px", padding: "14px 16px", background: "var(--surface)", border: "1px solid var(--accent)", borderRadius: 14 }}>
      <div style={{ fontSize: 14, fontWeight: 600, marginBottom: detail ? 8 : 12 }}>{title}</div>
      {detail && (
        <pre style={{ margin: "0 0 12px", padding: "8px 10px", background: "var(--bg2)", borderRadius: 8, fontSize: 12, color: "var(--text-mid)", whiteSpace: "pre-wrap", wordBreak: "break-word", maxHeight: 160, overflow: "auto", fontFamily: "var(--mono)" }}>{detail}</pre>
      )}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        <button style={{ ...btn, background: "var(--accent)", borderColor: "var(--accent)", color: "#000", fontWeight: 600 }} onClick={() => onChoose("once")}>Allow once</button>
        <button style={btn} onClick={() => onChoose("session")}>This session</button>
        <button style={btn} onClick={() => onChoose("always")}>Always</button>
        <button style={{ ...btn, marginInlineStart: "auto", color: "var(--red)" }} onClick={() => onChoose("cancel")}>Cancel</button>
      </div>
    </div>
  );
}
