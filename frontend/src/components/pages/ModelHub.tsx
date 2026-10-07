import { useCallback, useEffect, useState } from "react";
import { hubCancel, hubDownload, hubDownloads, hubFiles, hubHardware, hubSearch } from "../../api";
import type { HubFile, HubHardware, HubJob, HubRepo } from "../../api";
import { card, ghostBtn, primaryBtn, Empty } from "./PageShell";

const FIT_LABEL: Record<HubFile["fit"], string> = {
  gpu: "Fits in GPU memory", split: "Split GPU + RAM", cpu: "CPU only", too_big: "Too big for this machine",
};
const FIT_COLOR: Record<HubFile["fit"], string> = {
  gpu: "var(--green, #3fb950)", split: "var(--accent)", cpu: "var(--text-dim)", too_big: "var(--red)",
};

const gb = (b: number) => `${(b / 1024 ** 3).toFixed(1)} GB`;
const mb = (b: number) => `${(b / 1024 ** 2).toFixed(1)} MB/s`;

export default function ModelHub({ installed }: { installed: string[] }) {
  const [hw, setHw] = useState<HubHardware | null>(null);
  const [query, setQuery] = useState("");
  const [repos, setRepos] = useState<HubRepo[]>([]);
  const [repo, setRepo] = useState("");
  const [files, setFiles] = useState<HubFile[]>([]);
  const [jobs, setJobs] = useState<HubJob[]>([]);
  const [moe, setMoe] = useState(false);
  const [uncensored, setUncensored] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const run = async (fn: () => Promise<void>) => {
    setBusy(true); setError("");
    try { await fn(); } catch (e) { setError(String((e as Error).message ?? e)); }
    finally { setBusy(false); }
  };

  const search = () => run(async () => { setRepo(""); setFiles([]); setRepos(await hubSearch(query, moe, uncensored)); });
  const open = (id: string) => run(async () => {
    setRepo(id);
    const d = await hubFiles(id);
    setHw(d.hardware); setFiles(d.files);
  });

  useEffect(() => { hubHardware().then(setHw).catch(() => undefined); }, []);
  useEffect(() => { void search(); }, [moe, uncensored]);  // eslint-disable-line react-hooks/exhaustive-deps

  const poll = useCallback(() => { hubDownloads().then(setJobs).catch(() => undefined); }, []);
  useEffect(() => {
    poll();
    const t = setInterval(poll, 1500);
    return () => clearInterval(t);
  }, [poll]);

  const download = (f: HubFile) => run(async () => { await hubDownload(repo, f.file, f.size); poll(); });
  const jobFor = (f: HubFile) => jobs.filter(j => j.repo === repo && j.file === f.file).at(-1);
  const has = (f: HubFile) => installed.some(n => n.startsWith(f.file.split("/").pop()!.replace(/\.gguf$/i, "")));

  return (
    <div>
      {hw && (
        <div style={{ fontSize: 12, color: "var(--text-dim)", marginBottom: 8 }}>
          {hw.gpu ? `${hw.gpu}${hw.vram_total_gb ? ` - ${hw.vram_total_gb} GB VRAM` : ""}` : "No GPU detected"} - {hw.cpu_cores}-core CPU - {hw.ram_total_gb} GB RAM.
          Speeds are estimates for this machine.
        </div>
      )}
      <div style={{ display: "flex", gap: 8, marginBottom: 10 }}>
        <input value={query} onChange={e => setQuery(e.target.value)} onKeyDown={e => e.key === "Enter" && void search()}
          placeholder="Search Hugging Face (e.g. gemma, qwen, llama)"
          style={{ flex: 1, background: "var(--bg2)", border: "1px solid var(--border)", borderRadius: 8, padding: "8px 12px", color: "var(--text)", fontSize: 13 }} />
        <button style={primaryBtn} disabled={busy} onClick={() => void search()}>Search</button>
      </div>
      <div style={{ display: "flex", gap: 16, marginBottom: 10, fontSize: 13, color: "var(--text-mid)" }}>
        <label style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <input type="checkbox" checked={moe} onChange={e => setMoe(e.target.checked)} /> MoE
        </label>
        <label style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <input type="checkbox" checked={uncensored} onChange={e => setUncensored(e.target.checked)} /> Uncensored (abliterated or uncensored)
        </label>
      </div>
      {error && <div style={{ color: "var(--red)", fontSize: 12, marginBottom: 8, wordBreak: "break-word" }}>{error}</div>}

      {!repo && repos.map(r => (
        <div key={r.id} style={{ ...card, cursor: "pointer", display: "flex", alignItems: "center" }} onClick={() => void open(r.id)}>
          <span style={{ flex: 1, fontSize: 13, wordBreak: "break-all" }}>{r.id}</span>
          <span style={{ fontSize: 11, color: "var(--text-dim)" }}>{r.downloads.toLocaleString()} downloads</span>
        </div>
      ))}
      {!repo && !busy && repos.length === 0 && <Empty text="No results." />}

      {repo && (
        <>
          <div style={{ display: "flex", alignItems: "center", gap: 8, margin: "4px 0 8px" }}>
            <button style={ghostBtn} onClick={() => { setRepo(""); setFiles([]); }}>Back</button>
            <span style={{ fontSize: 13, fontWeight: 600, wordBreak: "break-all" }}>{repo}</span>
          </div>
          {!busy && files.length === 0 && <Empty text="No downloadable GGUF files in this repository." />}
          {files.map(f => {
            const j = jobFor(f);
            const active = j?.state === "downloading";
            return (
              <div key={f.file} style={card}>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, wordBreak: "break-all" }}>{f.file}</div>
                    <div style={{ fontSize: 12, color: "var(--text-dim)", marginTop: 3 }}>
                      {f.moe ? "MoE" : "Dense"} - {f.quant || "GGUF"} - {gb(f.size)} - <span style={{ color: FIT_COLOR[f.fit] }}>{FIT_LABEL[f.fit]}</span>
                      {f.fit !== "too_big" && <> - about {f.tps} tok/s</>}
                    </div>
                  </div>
                  {active
                    ? <button style={ghostBtn} onClick={() => void hubCancel(j!.id).then(poll)}>Cancel</button>
                    : <button style={primaryBtn} disabled={busy || j?.state === "done" || has(f)} onClick={() => void download(f)}>
                        {j?.state === "done" || has(f) ? "Installed" : "Download"}
                      </button>}
                </div>
                {active && (
                  <div style={{ marginTop: 8 }}>
                    <div style={{ height: 4, background: "var(--bg2)", borderRadius: 2 }}>
                      <div style={{ height: 4, borderRadius: 2, background: "var(--accent)", width: `${j!.total ? Math.min(100, j!.done / j!.total * 100) : 0}%` }} />
                    </div>
                    <div style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 3 }}>
                      {gb(j!.done)} / {gb(j!.total)} - {mb(j!.speed)}
                    </div>
                  </div>
                )}
                {j?.state === "error" && <div style={{ color: "var(--red)", fontSize: 12, marginTop: 6 }}>{j.error}</div>}
              </div>
            );
          })}
        </>
      )}
    </div>
  );
}
