import type { ModelState } from "../api";

export const STATE_COLORS = {
  idle: "#86868b", reading: "#4c8dff", generating: "#f97316", queued: "#f5c542", error: "#ff453a",
} as const;

const TITLES = { idle: "Idle", reading: "Reading", generating: "Generating", queued: "Loading model", error: "Error" } as const;

/** Round indicator of what the model is doing: grey idle, blue reading (fills with progress), orange generating, yellow loading, red error. */
export default function StateDot({ s, size = 20 }: { s: ModelState | null; size?: number }) {
  const state = s?.state ?? "idle";
  const color = STATE_COLORS[state];
  const r = size / 2 - 2;
  const c = 2 * Math.PI * r;
  const filled = state === "reading" ? c * Math.min(1, Math.max(0.04, s?.progress ?? 0)) : state === "idle" ? 0 : c;
  const title = `${TITLES[state]}${state === "reading" ? ` ${Math.round((s?.progress ?? 0) * 100)}%` : ""}${s?.detail ? ` - ${s.detail}` : ""}`;
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ display: "block", flexShrink: 0 }}>
      <title>{title}</title>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--border2)" strokeWidth={2} />
      {state !== "idle" && (
        <g transform={`rotate(-90 ${size / 2} ${size / 2})`}>
          <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={2} strokeLinecap="round"
            strokeDasharray={state === "generating" ? `${c * 0.3} ${c}` : `${filled} ${c}`}
            style={{
              transformBox: "fill-box", transformOrigin: "center",
              animation: state === "generating" ? "herama-spin 1s linear infinite" : state === "queued" ? "herama-pulse 1.1s ease-in-out infinite" : undefined,
            }} />
        </g>
      )}
      <circle cx={size / 2} cy={size / 2} r={size / 6} fill={color} style={{ animation: state === "queued" ? "herama-pulse 1.1s ease-in-out infinite" : undefined }} />
    </svg>
  );
}
