import { useEffect, useState } from "react";
import type { FsEntry } from "../../env";

interface Props { root: string; onPickRoot: (dir: string) => void }

const SEP = (p: string) => (p.includes("\\") ? "\\" : "/");

function Node({ dir, entry, depth, onOpen }: { dir: string; entry: FsEntry; depth: number; onOpen: (f: string) => void }) {
  const full = `${dir}${SEP(dir)}${entry.name}`;
  const [open, setOpen] = useState(false);
  const [kids, setKids] = useState<FsEntry[] | null>(null);

  const toggle = async () => {
    if (!entry.isDir) { onOpen(full); return; }
    if (!open && !kids) {
      try { setKids(await window.herama.fsList(full)); } catch { setKids([]); }
    }
    setOpen(o => !o);
  };

  return (
    <div>
      <div onClick={toggle} style={{ padding: "2px 8px", paddingLeft: 8 + depth * 14, cursor: "pointer", fontSize: 12, display: "flex", gap: 6, color: entry.isDir ? "var(--text)" : "var(--text-mid)" }}>
        <span style={{ width: 10, color: "var(--text-dim)" }}>{entry.isDir ? (open ? "v" : ">") : ""}</span>
        <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{entry.name}</span>
      </div>
      {open && kids?.map(k => <Node key={k.name} dir={full} entry={k} depth={depth + 1} onOpen={onOpen} />)}
    </div>
  );
}

export default function FilesPanel({ root, onPickRoot }: Props) {
  const [entries, setEntries] = useState<FsEntry[]>([]);
  const [preview, setPreview] = useState<{ file: string; text: string } | null>(null);

  useEffect(() => {
    if (!root) return;
    window.herama.fsList(root).then(setEntries).catch(() => setEntries([]));
    setPreview(null);
  }, [root]);

  const open = async (file: string) => {
    try { setPreview({ file, text: await window.herama.fsRead(file) }); }
    catch { setPreview({ file, text: "[cannot read file]" }); }
  };

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 10px", fontSize: 11, color: "var(--text-dim)" }}>
        <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={root}>{root}</span>
        <button onClick={async () => { const d = await window.herama.pickFolder(); if (d) onPickRoot(d); }}
          style={{ color: "var(--accent)", fontSize: 11 }}>open folder</button>
      </div>
      <div style={{ flex: 1, overflow: "auto", minHeight: 0 }}>
        {entries.map(e => <Node key={e.name} dir={root} entry={e} depth={0} onOpen={open} />)}
      </div>
      {preview && (
        <div style={{ height: "40%", display: "flex", flexDirection: "column", borderTop: "1px solid var(--border)" }}>
          <div style={{ display: "flex", padding: "4px 10px", fontSize: 11, color: "var(--text-dim)" }}>
            <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{preview.file}</span>
            <button onClick={() => setPreview(null)} style={{ color: "var(--text-dim)" }}>×</button>
          </div>
          <pre style={{ flex: 1, overflow: "auto", margin: 0, padding: "0 10px 8px", fontSize: 11, color: "var(--text-mid)" }}>{preview.text}</pre>
        </div>
      )}
    </div>
  );
}
