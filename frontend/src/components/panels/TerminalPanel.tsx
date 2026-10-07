import { useEffect, useRef, useState } from "react";
import type { TaskApi } from "../../types";

interface Props { cwd: string; tasks: TaskApi }

const ANSI = /\u001b\[[0-9;?]*[ -/]*[@-~]/g;
let seq = 0;

export default function TerminalPanel({ cwd, tasks }: Props) {
  const [dir, setDir] = useState(cwd);
  const [out, setOut] = useState("");
  const [input, setInput] = useState("");
  const [running, setRunning] = useState<string | null>(null);
  const taskIds = useRef(new Map<string, string>());
  const endRef = useRef<HTMLDivElement>(null);
  const hist = useRef<string[]>([]);
  const histPos = useRef(0);

  useEffect(() => { setDir(cwd); }, [cwd]);
  useEffect(() => { endRef.current?.scrollIntoView(); }, [out]);

  useEffect(() => {
    return window.herama.onTermData(m => {
      if (m.data) setOut(o => (o + m.data.replace(ANSI, "")).slice(-60_000));
      if (m.code !== undefined) {
        setRunning(r => (r === m.id ? null : r));
        const tid = taskIds.current.get(m.id);
        if (tid) { tasks.finish(tid, m.code === 0 ? "done" : "error"); taskIds.current.delete(m.id); }
      }
    });
  }, [tasks]);

  const run = async () => {
    const cmd = input.trim();
    if (!cmd || running) return;
    hist.current.push(cmd);
    histPos.current = hist.current.length;
    setInput("");
    setOut(o => `${o}\n$ ${cmd}\n`);
    if (cmd === "clear" || cmd === "cls") { setOut(""); return; }
    const cd = /^cd\s+(.+)$/i.exec(cmd);
    if (cd) {
      const target = await window.herama.fsResolve(dir, cd[1].replace(/^"|"$/g, ""));
      if (target) setDir(target); else setOut(o => `${o}no such directory\n`);
      return;
    }
    const id = `t${++seq}`;
    setRunning(id);
    taskIds.current.set(id, tasks.start(`terminal: ${cmd.slice(0, 40)}`));
    await window.herama.termRun(id, cmd, dir);
  };

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") run();
    else if (e.key === "ArrowUp" && hist.current.length) {
      histPos.current = Math.max(0, histPos.current - 1);
      setInput(hist.current[histPos.current]);
    } else if (e.key === "ArrowDown") {
      histPos.current = Math.min(hist.current.length, histPos.current + 1);
      setInput(hist.current[histPos.current] ?? "");
    } else if (e.key === "c" && e.ctrlKey && running) {
      window.herama.termKill(running);
    }
  };

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0, background: "#0d0d0e", fontFamily: "var(--mono)", fontSize: 12 }}>
      <div style={{ flex: 1, overflow: "auto", padding: "8px 10px", whiteSpace: "pre-wrap", wordBreak: "break-all", color: "var(--text-mid)" }}>
        {out}
        <div ref={endRef} />
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "6px 10px", borderTop: "1px solid var(--border)" }}>
        <span style={{ color: "var(--accent)", maxWidth: 140, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={dir}>{dir.split(/[\\/]/).filter(Boolean).pop() ?? dir}</span>
        <span style={{ color: "var(--text-dim)" }}>$</span>
        <input value={input} onChange={e => setInput(e.target.value)} onKeyDown={onKey}
          placeholder={running ? "running... (Ctrl+C to stop)" : "command"} style={{ flex: 1, fontFamily: "var(--mono)", fontSize: 12 }} />
        {running && <button onClick={() => window.herama.termKill(running)} style={{ color: "var(--red)", fontSize: 11 }}>stop</button>}
      </div>
    </div>
  );
}
