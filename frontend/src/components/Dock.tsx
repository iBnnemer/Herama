import { useRef } from "react";
import { PANELS } from "../types";
import type { PanelId, Task, TaskApi } from "../types";
import TasksPanel from "./panels/TasksPanel";
import PlanPanel from "./panels/PlanPanel";
import BrowserPanel from "./panels/BrowserPanel";
import TerminalPanel from "./panels/TerminalPanel";
import FilesPanel from "./panels/FilesPanel";

interface Props {
  open: PanelId[];
  width: number;
  onWidth: (w: number) => void;
  onClose: (id: PanelId) => void;
  tasks: Task[];
  taskApi: TaskApi;
  onClearTasks: () => void;
  projectDir: string;
  onProjectDir: (d: string) => void;
}

export default function Dock(p: Props) {
  const drag = useRef(false);

  const startDrag = (e: React.MouseEvent) => {
    e.preventDefault();
    drag.current = true;
    const move = (ev: MouseEvent) => {
      if (drag.current) p.onWidth(Math.min(900, Math.max(280, window.innerWidth - ev.clientX)));
    };
    const up = () => {
      drag.current = false;
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
    };
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
  };

  const body = (id: PanelId) => {
    switch (id) {
      case "tasks":    return <TasksPanel tasks={p.tasks} onClear={p.onClearTasks} />;
      case "plan":     return <PlanPanel />;
      case "browser":  return <BrowserPanel />;
      case "terminal": return <TerminalPanel cwd={p.projectDir} tasks={p.taskApi} />;
      case "files":    return <FilesPanel root={p.projectDir} onPickRoot={p.onProjectDir} />;
    }
  };

  const shown = PANELS.filter(x => p.open.includes(x.id));
  if (shown.length === 0) return null;

  return (
    <aside style={{ width: p.width, flexShrink: 0, display: "flex", background: "var(--bg2)", borderLeft: "1px solid var(--border)" }}>
      <div onMouseDown={startDrag} style={{ width: 4, cursor: "col-resize", flexShrink: 0 }} />
      <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
        {shown.map((x, i) => (
          <section key={x.id} style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column", borderTop: i ? "1px solid var(--border)" : "none" }}>
            <header style={{ display: "flex", alignItems: "center", padding: "6px 12px", fontSize: 11, color: "var(--text-dim)", letterSpacing: "0.06em", textTransform: "uppercase", flexShrink: 0 }}>
              <span style={{ flex: 1 }}>{x.title}</span>
              <button onClick={() => p.onClose(x.id)} title="close" style={{ color: "var(--text-dim)", fontSize: 15, lineHeight: 1 }}>×</button>
            </header>
            {body(x.id)}
          </section>
        ))}
      </div>
    </aside>
  );
}
