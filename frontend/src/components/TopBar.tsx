interface Props {
  title: string;
  connected: boolean;
  tps: number;
}

export default function TopBar({ title, connected, tps }: Props) {
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 10,
      padding: "10px 20px", borderBottom: "1px solid var(--border)",
      background: "var(--surface)", flexShrink: 0, height: 42,
      WebkitAppRegion: "drag" as unknown as undefined,
    }}>
      <span style={{ color: "var(--text-mid)", fontSize: 12 }}>{title}</span>
      <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 6, fontSize: 10, color: "var(--text-dim)" }}>
        <span style={{
          width: 6, height: 6, borderRadius: "50%",
          background: connected ? "#22c55e" : "var(--border2)",
          display: "inline-block",
        }} />
        <span>{connected ? (tps > 0 ? `${tps.toFixed(1)} t/s` : "online") : "offline"}</span>
      </div>
    </div>
  );
}
