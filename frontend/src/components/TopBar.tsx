import { PANELS } from "../types";
import type { PanelId } from "../types";
import Icon from "./Icons";
import type { IconName } from "./Icons";

interface Props {
  title: string;
  connected: boolean;
  tps: number;
  leftOpen: boolean;
  onToggleLeft: () => void;
  openPanels: PanelId[];
  onTogglePanel: (id: PanelId) => void;
  onOpenMonitor: () => void;
  theme: "dark" | "light";
  onToggleTheme: () => void;
}

const tbtn: React.CSSProperties = {
  padding: 6, borderRadius: 7, color: "var(--text-mid)", border: "1px solid transparent", display: "flex",
};

export default function TopBar(p: Props) {
  return (
    <div className="titlebar" style={{
      height: 44, display: "flex", alignItems: "center", padding: "0 20px",
      borderBottom: "1px solid var(--border)", flexShrink: 0, gap: 10,
    }}>
      <button onClick={p.onToggleLeft} title={p.leftOpen ? "hide sidebar" : "show sidebar"}
        style={{ ...tbtn, background: p.leftOpen ? "var(--surface2)" : "transparent" }}>
        <Icon name="sidebar" />
      </button>
      <span style={{ fontSize: 13, color: "var(--text-mid)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {p.title}
      </span>
      <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 4 }}>
        {PANELS.map(x => {
          const on = p.openPanels.includes(x.id);
          return (
            <button key={x.id} onClick={() => p.onTogglePanel(x.id)} title={x.title}
              style={{ ...tbtn, background: on ? "var(--surface2)" : "transparent", color: on ? "var(--text)" : "var(--text-dim)" }}>
              <Icon name={x.id as IconName} />
            </button>
          );
        })}
      </div>
      <button onClick={p.onOpenMonitor} title="monitor" style={{ ...tbtn, color: "var(--text-dim)" }}><Icon name="gauge" /></button>
      <button onClick={p.onToggleTheme} title={p.theme === "dark" ? "switch to light mode" : "switch to dark mode"} style={{ ...tbtn, color: "var(--text-dim)" }}>
        <Icon name={p.theme === "dark" ? "sun" : "moon"} />
      </button>
      <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: "var(--text-dim)", marginLeft: 8 }}>
        <span style={{ width: 7, height: 7, borderRadius: "50%", flexShrink: 0, background: p.connected ? "var(--green)" : "var(--border2)" }} />
      </div>
    </div>
  );
}
