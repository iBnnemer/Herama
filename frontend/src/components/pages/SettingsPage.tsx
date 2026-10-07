import { useEffect, useMemo, useRef, useState } from "react";
import type { AppState, Conversation, Effort, Safety } from "../../types";
import { EFFORT_LEVELS, EFFORT_PARAMS } from "../../types";
import type { Prefs } from "../../prefs";
import { BASE, deleteProvider, fetchSkills, listProviders, loadTools, saveProvider, testProvider } from "../../api";
import type { ApiProvider, ToolInfo } from "../../api";
import { approvals, describeKey } from "../../approvals";
import Icon from "../Icons";
import { card, ghostBtn, primaryBtn, Empty } from "./PageShell";
import ModelHub from "./ModelHub";

interface Props {
  state: AppState;
  theme: "dark" | "light";
  onTheme: (t: "dark" | "light") => void;
  prefs: Prefs;
  onPrefs: (p: Prefs) => void;
  conversations: Conversation[];
  onClearSessions: () => void;
  projectDir: string;
  onProjectDir: (d: string) => void;
  onModel: (m: string) => void;
  onContext: (n: number) => void;
  onEffort: (e: Effort) => void;
  onSafety: (s: Safety) => void;
  onModelsChanged: () => void;
  target?: string;
}

interface Sub { id: string; label: string; keys?: string }
interface Section { id: string; label: string; subs: Sub[] }

const SECTIONS: Section[] = [
  { id: "model", label: "Model", subs: [{ id: "main", label: "Main model", keys: "context window reasoning effort" }] },
  { id: "appearance", label: "Appearance", subs: [{ id: "theme", label: "Theme", keys: "dark light" }, { id: "typography", label: "Typography", keys: "scale zoom size font" }] },
  { id: "safety", label: "Safety", subs: [{ id: "approvals", label: "Approvals", keys: "ask plan auto off commands allowed" }] },
  { id: "memory", label: "Memory & Context", subs: [{ id: "facts", label: "Persistent memory", keys: "remember facts" }, { id: "context", label: "Context & compression", keys: "summary summarize" }] },
  { id: "tools", label: "Tools", subs: [{ id: "list", label: "Agent tools", keys: "files web shell git schedule" }] },
  { id: "providers", label: "Providers", subs: [{ id: "local", label: "Local models", keys: "gguf hugging face download" }, { id: "api", label: "API models", keys: "external openai openrouter groq deepseek key endpoint url" }] },
  { id: "sessions", label: "Sessions", subs: [{ id: "retention", label: "Archive & retention", keys: "delete old history" }, { id: "folder", label: "Default project folder", keys: "directory workspace" }] },
  { id: "plugins", label: "Plugins", subs: [{ id: "skills", label: "Skills", keys: "plugins generated" }] },
  { id: "about", label: "About", subs: [{ id: "version", label: "Version & updates", keys: "update version engine" }] },
];

const CTX_STEPS = [4096, 8192, 16384, 32768, 65536, 131072, 262144];
const fmtCtx = (n: number) => (n >= 1024 ? `${Math.round(n / 1024)}K` : String(n));
const SAFETY: { id: Safety; label: string; hint: string }[] = [
  { id: "ask", label: "Ask", hint: "Ask for approval before changing files or running commands." },
  { id: "plan", label: "Plan", hint: "Read only: the model proposes steps and runs nothing." },
  { id: "auto", label: "Auto", hint: "Run commands without asking (git push is still always asked)." },
  { id: "off", label: "Off", hint: "No tools at all." },
];

const input: React.CSSProperties = { maxWidth: "100%", textOverflow: "ellipsis", background: "var(--bg2)", border: "1px solid var(--border)", borderRadius: 8, padding: "6px 10px", color: "var(--text)", fontSize: 13 };

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div style={{ ...card, display: "flex", alignItems: "center", gap: 16 }}>
      <div style={{ flex: 1, minWidth: 140 }}>
        <div style={{ fontSize: 13, fontWeight: 600 }}>{label}</div>
        {hint && <div style={{ fontSize: 12, color: "var(--text-dim)", marginTop: 2, lineHeight: 1.5 }}>{hint}</div>}
      </div>
      <div style={{ flexShrink: 0, maxWidth: "50%" }}>{children}</div>
    </div>
  );
}

function Segmented<T extends string>({ value, items, onPick }: { value: T; items: { id: T; label: string }[]; onPick: (v: T) => void }) {
  return (
    <div style={{ display: "flex", gap: 2, background: "var(--bg2)", border: "1px solid var(--border)", borderRadius: 8, padding: 2 }}>
      {items.map(i => (
        <button key={i.id} onClick={() => onPick(i.id)} style={{
          padding: "4px 12px", borderRadius: 6, fontSize: 12,
          background: value === i.id ? "var(--accent)" : "transparent", color: value === i.id ? "#000" : "var(--text-mid)", fontWeight: value === i.id ? 600 : 400,
        }}>{i.label}</button>
      ))}
    </div>
  );
}

function Facts({ connected }: { connected: boolean }) {
  const [facts, setFacts] = useState<{ id: number; content: string; agent?: string }[]>([]);
  const [names, setNames] = useState<Record<string, string>>({});
  const load = () => fetch(`${BASE}/api/memory?k=100`).then(r => r.json()).then(d => setFacts(Array.isArray(d) ? d : d.facts ?? [])).catch(() => setFacts([]));
  useEffect(() => {
    if (!connected) return;
    void load();
    fetch(`${BASE}/api/agents`).then(r => r.json()).then((l: { id: string; name: string }[]) => setNames(Object.fromEntries(l.map(a => [a.id, a.name])))).catch(() => {});
  }, [connected]);
  if (!connected) return <Empty text="Backend offline." />;
  return (
    <>
      <div style={{ fontSize: 12, color: "var(--text-dim)", marginBottom: 10 }}>Facts agents saved with the remember tool. Relevant ones are given to the model automatically; each agent sees its own plus the shared ones.</div>
      {facts.length === 0 && <Empty text="No remembered facts yet." />}
      {facts.map(f => (
        <div key={f.id} style={{ ...card, display: "flex", alignItems: "center", gap: 10, fontSize: 13 }}>
          <span style={{ flex: 1, wordBreak: "break-word" }}>{f.content}</span>
          <span style={{ fontSize: 11, color: "var(--text-dim)" }}>{f.agent ? names[f.agent] ?? f.agent : "shared"}</span>
          <button style={ghostBtn} onClick={() => void fetch(`${BASE}/api/memory/${f.id}`, { method: "DELETE" }).then(load).catch(() => {})}>Delete</button>
        </div>
      ))}
    </>
  );
}

function ToolsList({ connected }: { connected: boolean }) {
  const [tools, setTools] = useState<ToolInfo[]>([]);
  useEffect(() => { if (connected) void loadTools().then(setTools); }, [connected]);
  if (!connected) return <Empty text="Backend offline." />;
  const groups = [...new Set(tools.map(t => t.group))];
  return (
    <>
      <div style={{ fontSize: 12, color: "var(--text-dim)", marginBottom: 10 }}>Only the groups your message needs are switched on; the model can switch on another itself.</div>
      {groups.map(g => (
        <div key={g} style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 12, color: "var(--text-mid)", margin: "8px 2px 6px" }}>{g}</div>
          <div style={{ ...card, padding: 0 }}>
            {tools.filter(t => t.group === g).map((t, i) => (
              <div key={t.name} style={{ padding: "10px 16px", borderTop: i ? "1px solid var(--border)" : "none" }}>
                <span style={{ fontWeight: 700, fontSize: 13 }}>{t.name}</span>
                <span style={{ fontSize: 10, color: "var(--text-dim)", border: "1px solid var(--border2)", borderRadius: 6, padding: "1px 6px", marginLeft: 8 }}>{t.kind}</span>
                <div style={{ color: "var(--text-dim)", fontSize: 12, marginTop: 3, lineHeight: 1.5 }}>{t.description}</div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </>
  );
}

function ApiModels({ connected, onSaved }: { connected: boolean; onSaved: () => void }) {
  const [presets, setPresets] = useState<Record<string, string>>({});
  const [items, setItems] = useState<ApiProvider[]>([]);
  const blank = { id: "", label: "", provider: "OpenAI", model: "", base_url: "", api_key: "" };
  const [f, setF] = useState(blank);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const load = () => listProviders().then(d => { setPresets(d.presets); setItems(d.items); if (!f.base_url && !f.id) setF(v => ({ ...v, base_url: d.presets[v.provider] ?? "" })); }).catch(() => {});
  useEffect(() => { if (connected) void load(); }, [connected]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!connected) return <Empty text="Backend offline." />;
  const set = (patch: Partial<typeof f>) => { setF(v => ({ ...v, ...patch })); setMsg(null); };
  const run = async (fn: () => Promise<void>) => { setBusy(true); try { await fn(); } catch (e) { setMsg({ ok: false, text: String((e as Error).message ?? e) }); } finally { setBusy(false); } };
  const row = (label: string, el: React.ReactNode) => <Field label={label}>{el}</Field>;
  return (
    <>
      <div style={{ fontSize: 12, color: "var(--text-dim)", marginBottom: 10, lineHeight: 1.6 }}>
        Use a model hosted by a provider that speaks the OpenAI chat API. Saved models appear in the model list as api:name. The key is stored only in this computer's .memory folder and is sent only to the address you enter. Conversations with an API model leave this computer.
      </div>
      {row("Provider", <select style={input} value={f.provider} onChange={e => set({ provider: e.target.value, base_url: presets[e.target.value] ?? f.base_url })}>{Object.keys(presets).map(k => <option key={k}>{k}</option>)}</select>)}
      {row("Model", <input style={{ ...input, width: 260 }} value={f.model} onChange={e => set({ model: e.target.value })} placeholder="e.g. gpt-4o-mini" />)}
      {row("API key", <input style={{ ...input, width: 260 }} type="password" value={f.api_key} onChange={e => set({ api_key: e.target.value })} placeholder={f.id && items.find(i => i.id === f.id)?.has_key ? "saved (leave empty to keep)" : "sk-..."} autoComplete="off" />)}
      {row("URL", <input style={{ ...input, width: 260 }} value={f.base_url} onChange={e => set({ base_url: e.target.value })} placeholder="https://.../v1" />)}
      {row("Name (optional)", <input style={{ ...input, width: 260 }} value={f.label} onChange={e => set({ label: e.target.value })} placeholder="shown in the model list" />)}
      <div style={{ display: "flex", gap: 8, alignItems: "center", margin: "6px 0 18px" }}>
        <button style={ghostBtn} disabled={busy} onClick={() => void run(async () => { const r = await testProvider(f); setMsg({ ok: r.ok, text: r.ok ? `Works. Reply: ${r.detail}` : r.detail }); })}>Test</button>
        <button style={primaryBtn} disabled={busy} onClick={() => void run(async () => { await saveProvider(f); setF(blank); setMsg({ ok: true, text: "Saved." }); await load(); onSaved(); })}>Save</button>
        {f.id && <button style={ghostBtn} onClick={() => { setF(blank); setMsg(null); }}>Cancel edit</button>}
        {msg && <span style={{ fontSize: 12, color: msg.ok ? "var(--green)" : "var(--red)", wordBreak: "break-word", minWidth: 0 }}>{msg.text}</span>}
      </div>
      <div style={{ fontSize: 12, color: "var(--text-mid)", margin: "0 2px 6px" }}>Saved</div>
      {items.length === 0 && <Empty text="No API models yet." />}
      {items.map(i => (
        <div key={i.id} style={{ ...card, display: "flex", alignItems: "center", gap: 10, fontSize: 13 }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontWeight: 600 }}>{i.label}</div>
            <div style={{ fontSize: 11, color: "var(--text-dim)", wordBreak: "break-all" }}>{i.provider} - {i.model} - {i.base_url}{i.has_key ? ` - key ...${i.key_hint}` : " - no key"}</div>
          </div>
          <button style={ghostBtn} onClick={() => { setF({ id: i.id, label: i.label, provider: i.provider, model: i.model, base_url: i.base_url, api_key: "" }); setMsg(null); }}>Edit</button>
          <button style={ghostBtn} onClick={() => void deleteProvider(i.id).then(() => { void load(); onSaved(); }).catch(() => {})}>Delete</button>
        </div>
      ))}
    </>
  );
}

function Version({ state }: { state: AppState }) {
  const [v, setV] = useState("");
  useEffect(() => { fetch(`${BASE}/api/version`).then(r => r.json()).then(d => setV(String(d.version ?? ""))).catch(() => setV("")); }, [state.connected]);
  return (
    <>
      <Field label="Backend version">{v || "unknown"}</Field>
      <Field label="Inference engine">{state.engine || "unknown"}</Field>
      <Field label="GPU acceleration">{state.accelerated === null ? "unknown" : state.accelerated ? "on" : "off"}</Field>
      <div style={{ fontSize: 12, color: "var(--text-dim)", marginTop: 10, lineHeight: 1.6 }}>To update, close the app and run UPDATE.bat. It downloads the latest version and starts the app again.</div>
    </>
  );
}

export default function SettingsPage(p: Props) {
  const [sel, setSel] = useState("model/main");
  const [open, setOpen] = useState<Record<string, boolean>>({ model: true });
  const [q, setQ] = useState("");
  const [granted, setGranted] = useState<string[]>(() => approvals.always());
  const [skills, setSkills] = useState<{ name: string; desc: string }[]>([]);
  const [confirmClear, setConfirmClear] = useState(false);
  const search = useRef<HTMLInputElement>(null);
  const { state } = p;
  useEffect(() => { if (p.target) setSel(p.target.split("@")[0]); }, [p.target]);

  useEffect(() => {
    const k = (e: KeyboardEvent) => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); search.current?.focus(); } };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, []);
  useEffect(() => { if (state.connected) void fetchSkills().then(setSkills); }, [state.connected]);

  const needle = q.trim().toLowerCase();
  const nav = useMemo(() => SECTIONS.map(s => ({
    ...s,
    subs: s.subs.filter(x => !needle || `${s.label} ${x.label} ${x.keys ?? ""}`.toLowerCase().includes(needle)),
  })).filter(s => s.subs.length), [needle]);

  const [secId, subId] = sel.split("/");
  const section = SECTIONS.find(s => s.id === secId) ?? SECTIONS[0];
  const sub = section.subs.find(s => s.id === subId) ?? section.subs[0];
  const ctxSteps = CTX_STEPS.includes(state.contextLength) ? CTX_STEPS : [...CTX_STEPS, state.contextLength].sort((a, b) => a - b);

  const content = (() => {
    switch (`${section.id}/${sub.id}`) {
      case "model/main":
        return (
          <>
            <Field label="Model" hint="Used for every new message. Models are .gguf files in the models folder.">
              <select style={input} value={state.activeModel} onChange={e => p.onModel(e.target.value)}>
                {state.models.length === 0 && <option value="">No models found</option>}
                {state.models.map(m => <option key={m.name} value={m.name}>{m.name.replace(/:latest$/, "")}</option>)}
              </select>
            </Field>
            <Field label="Context window" hint="Larger contexts remember more and use more memory. Manual GPU/CPU layout is under the gear in the chat box.">
              <select style={input} value={state.contextLength} onChange={e => p.onContext(+e.target.value)}>
                {ctxSteps.map(n => <option key={n} value={n}>{fmtCtx(n)} tokens</option>)}
              </select>
            </Field>
            <Field label="Reasoning level" hint="Higher levels make answers more varied and creative; lower levels are steadier.">
              <Segmented value={state.effort} items={EFFORT_LEVELS.map(e => ({ id: e, label: EFFORT_PARAMS[e].label }))} onPick={p.onEffort} />
            </Field>
          </>
        );
      case "appearance/theme":
        return (
          <Field label="Theme">
            <Segmented value={p.theme} items={[{ id: "dark", label: "Dark" }, { id: "light", label: "Light" }]} onPick={p.onTheme} />
          </Field>
        );
      case "appearance/typography":
        return (
          <Field label="Interface scale" hint="Makes the whole app larger or smaller.">
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <input type="range" min={75} max={150} step={5} value={p.prefs.scale} onChange={e => p.onPrefs({ ...p.prefs, scale: +e.target.value })} style={{ accentColor: "var(--accent)" }} />
              <span style={{ fontSize: 12, width: 40 }}>{p.prefs.scale}%</span>
              <button style={ghostBtn} onClick={() => p.onPrefs({ ...p.prefs, scale: 100 })}>Reset</button>
            </div>
          </Field>
        );
      case "safety/approvals":
        return (
          <>
            <Field label="Commands and file changes" hint={SAFETY.find(s => s.id === state.safety)?.hint}>
              <Segmented value={state.safety} items={SAFETY.map(s => ({ id: s.id, label: s.label }))} onPick={p.onSafety} />
            </Field>
            <div style={{ fontSize: 12, color: "var(--text-mid)", margin: "14px 2px 6px" }}>Always allowed</div>
            {granted.length === 0 && <Empty text="Nothing is always allowed. Approvals you choose to remember appear here." />}
            {granted.map(k => (
              <div key={k} style={{ ...card, display: "flex", alignItems: "center", gap: 10, fontSize: 13 }}>
                <span style={{ flex: 1, wordBreak: "break-all" }}>{describeKey(k)}</span>
                <button style={ghostBtn} onClick={() => { approvals.forget(k); setGranted(approvals.always()); }}>Remove</button>
              </div>
            ))}
          </>
        );
      case "memory/facts": return <Facts connected={state.connected} />;
      case "memory/context":
        return (
          <>
            <Field label="Automatic summary" hint="When a conversation outgrows the context window, older messages are condensed into a short summary so the chat can go on.">On</Field>
            <Field label="Current context window">{fmtCtx(state.contextLength)} tokens</Field>
          </>
        );
      case "tools/list": return <ToolsList connected={state.connected} />;
      case "providers/local":
        return (
          <>
            <div style={{ fontSize: 12, color: "var(--text-mid)", margin: "0 2px 6px" }}>Installed</div>
            {state.models.length === 0 && <Empty text="No models found. Put .gguf files in the models folder or download one below." />}
            {state.models.map(m => <div key={m.name} style={card}>{m.name.replace(/:latest$/, "")}</div>)}
            <div style={{ fontSize: 12, color: "var(--text-mid)", margin: "18px 2px 8px" }}>Search and download (Hugging Face)</div>
            {state.connected ? <ModelHub installed={state.models.map(m => m.name)} /> : <Empty text="Backend offline." />}
          </>
        );
      case "providers/api": return <ApiModels connected={state.connected} onSaved={p.onModelsChanged} />;
      case "sessions/retention":
        return (
          <>
            <Field label="Delete old sessions" hint="Sessions with no activity for this long are removed when the app starts. Pinned sessions are kept.">
              <select style={input} value={p.prefs.retentionDays} onChange={e => p.onPrefs({ ...p.prefs, retentionDays: +e.target.value })}>
                <option value={0}>Never</option><option value={7}>After 7 days</option><option value={30}>After 30 days</option><option value={90}>After 90 days</option>
              </select>
            </Field>
            <Field label="Clear all sessions" hint={`${p.conversations.length} session${p.conversations.length === 1 ? "" : "s"} stored on this computer.`}>
              {confirmClear ? (
                <span style={{ display: "flex", gap: 6 }}>
                  <button style={{ ...ghostBtn, color: "var(--red)" }} onClick={() => { p.onClearSessions(); setConfirmClear(false); }}>Confirm</button>
                  <button style={ghostBtn} onClick={() => setConfirmClear(false)}>Cancel</button>
                </span>
              ) : <button style={ghostBtn} onClick={() => setConfirmClear(true)}>Clear</button>}
            </Field>
          </>
        );
      case "sessions/folder":
        return (
          <Field label="Default project folder" hint="Folder used by files, terminal and browser panels when no project is selected.">
            <input style={{ ...input, width: 280 }} value={p.projectDir} onChange={e => p.onProjectDir(e.target.value)} placeholder="not set" />
          </Field>
        );
      case "plugins/skills":
        return (
          <>
            {skills.length === 0 && <Empty text="No skills yet. Skills are generated by the backend and saved in the skills folder." />}
            {skills.map(s => (
              <div key={s.name} style={card}>
                <div style={{ fontWeight: 600, fontSize: 13 }}>{s.name}</div>
                {s.desc && <div style={{ color: "var(--text-dim)", fontSize: 12, marginTop: 2 }}>{s.desc}</div>}
              </div>
            ))}
          </>
        );
      case "about/version": return <Version state={state} />;
      default: return null;
    }
  })();

  return (
    <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
      <nav style={{ width: 240, flexShrink: 0, borderRight: "1px solid var(--border)", padding: 10, overflow: "auto", background: "var(--bg2)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, padding: "6px 10px", marginBottom: 10 }}>
          <Icon name="search" size={14} />
          <input ref={search} value={q} onChange={e => setQ(e.target.value)} placeholder="Search" style={{ flex: 1, minWidth: 0, background: "transparent", border: "none", outline: "none", color: "var(--text)", fontSize: 13 }} />
          <span style={{ fontSize: 10, color: "var(--text-dim)" }}>Ctrl K</span>
        </div>
        {nav.length === 0 && <Empty text="No matching settings." />}
        {nav.map(s => {
          const expanded = !!needle || open[s.id];
          return (
            <div key={s.id}>
              <button onClick={() => { setOpen(o => ({ ...o, [s.id]: !o[s.id] })); if (!expanded) setSel(`${s.id}/${s.subs[0].id}`); }} style={{
                width: "100%", display: "flex", alignItems: "center", padding: "7px 10px", borderRadius: 8, fontSize: 13, textAlign: "left",
                color: section.id === s.id ? "var(--text)" : "var(--text-mid)",
              }}>
                <span style={{ flex: 1 }}>{s.label}</span>
                <span style={{ display: "flex", transform: expanded ? "none" : "rotate(-90deg)" }}><Icon name="chevron" size={13} /></span>
              </button>
              {expanded && s.subs.map(x => (
                <button key={x.id} onClick={() => setSel(`${s.id}/${x.id}`)} style={{
                  width: "100%", textAlign: "left", padding: "6px 10px 6px 24px", borderRadius: 8, fontSize: 12.5,
                  background: sel === `${s.id}/${x.id}` ? "var(--surface2)" : "transparent",
                  color: sel === `${s.id}/${x.id}` ? "var(--text)" : "var(--text-dim)",
                }}>{x.label}</button>
              ))}
            </div>
          );
        })}
      </nav>
      <div style={{ flex: 1, overflow: "auto", padding: "28px 0" }}>
        <div style={{ maxWidth: 720, margin: "0 auto", padding: "0 24px" }}>
          <div style={{ fontSize: 12, color: "var(--text-dim)", marginBottom: 4 }}>Settings &gt; {section.label} &gt; {sub.label}</div>
          <h1 style={{ fontSize: 20, fontWeight: 600, marginBottom: 18 }}>{sub.label}</h1>
          {content}
        </div>
      </div>
    </div>
  );
}
