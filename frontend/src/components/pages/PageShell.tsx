export default function PageShell({ title, hint, action, children }: { title: string; hint?: string; action?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div style={{ flex: 1, overflow: "auto", padding: "28px 0" }}>
      <div style={{ maxWidth: 760, margin: "0 auto", padding: "0 24px" }}>
        <div style={{ display: "flex", alignItems: "center", marginBottom: 6 }}>
          <h1 style={{ fontSize: 20, fontWeight: 600, flex: 1 }}>{title}</h1>
          {action}
        </div>
        {hint && <p style={{ color: "var(--text-dim)", fontSize: 13, marginBottom: 20 }}>{hint}</p>}
        {children}
      </div>
    </div>
  );
}

export const card: React.CSSProperties = {
  background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 10, padding: "12px 14px", marginBottom: 8,
};

export const primaryBtn: React.CSSProperties = {
  padding: "6px 14px", background: "var(--accent)", color: "#000", borderRadius: 8, fontWeight: 600, fontSize: 13,
};

export const ghostBtn: React.CSSProperties = {
  padding: "5px 12px", border: "1px solid var(--border)", borderRadius: 8, color: "var(--text-mid)", fontSize: 12,
};

export function Empty({ text }: { text: string }) {
  return <div style={{ color: "var(--text-dim)", fontSize: 13, padding: "24px 0", textAlign: "center" }}>{text}</div>;
}
