import { useEffect, useRef, useState } from "react";
import Icon from "../Icons";

const Webview = "webview" as unknown as React.ElementType;
const HOME = "https://duckduckgo.com";

function normalize(input: string): string {
  const v = input.trim();
  if (/^https?:\/\//i.test(v)) return v;
  if (/^[\w-]+(\.[\w-]+)+(\/.*)?$/.test(v) || /^localhost(:\d+)?/.test(v)) return `http://${v}`;
  return `https://duckduckgo.com/?q=${encodeURIComponent(v)}`;
}

type WebviewEl = HTMLElement & {
  loadURL: (u: string) => void; goBack: () => void; goForward: () => void; reload: () => void; stop: () => void;
  canGoBack: () => boolean; canGoForward: () => boolean;
};

export default function BrowserPanel() {
  const ref = useRef<WebviewEl | null>(null);
  const [url, setUrl] = useState(HOME);
  const [addr, setAddr] = useState(HOME);
  const [nav, setNav] = useState({ back: false, forward: false, loading: false });

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const sync = (loading?: boolean) => {
      try { setNav(n => ({ back: el.canGoBack(), forward: el.canGoForward(), loading: loading ?? n.loading })); } catch { /* webview not ready yet */ }
    };
    const onNav = (e: Event) => {
      const u = (e as Event & { url?: string }).url;
      if (u) { setUrl(u); setAddr(u); }
      sync();
    };
    const onStart = () => sync(true);
    const onStop = () => sync(false);
    el.addEventListener("did-start-loading", onStart);
    el.addEventListener("did-stop-loading", onStop);
    el.addEventListener("did-navigate", onNav);
    el.addEventListener("did-navigate-in-page", onNav);
    return () => {
      el.removeEventListener("did-navigate", onNav);
      el.removeEventListener("did-navigate-in-page", onNav);
      el.removeEventListener("did-start-loading", onStart);
      el.removeEventListener("did-stop-loading", onStop);
    };
  }, []);

  const btn = (enabled = true): React.CSSProperties => ({
    width: 30, height: 30, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center",
    color: enabled ? "var(--text-mid)" : "var(--text-dim)", opacity: enabled ? 1 : 0.4, cursor: enabled ? "pointer" : "default",
  });

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0 }}>
      <div style={{ display: "flex", gap: 2, padding: 6, alignItems: "center" }}>
        <button className="msg-btn" style={btn(nav.back)} title="back" disabled={!nav.back} onClick={() => ref.current?.goBack()}><Icon name="back" size={17} /></button>
        <button className="msg-btn" style={btn(nav.forward)} title="forward" disabled={!nav.forward} onClick={() => ref.current?.goForward()}><Icon name="forward" size={17} /></button>
        <button className="msg-btn" style={btn()} title={nav.loading ? "stop" : "reload"} onClick={() => (nav.loading ? ref.current?.stop() : ref.current?.reload())}>
          <Icon name={nav.loading ? "close" : "reload"} size={17} />
        </button>
        <button className="msg-btn" style={btn()} title="home" onClick={() => ref.current?.loadURL(HOME)}><Icon name="home" size={17} /></button>
        <input value={addr} onChange={e => setAddr(e.target.value)}
          onKeyDown={e => { if (e.key === "Enter") ref.current?.loadURL(normalize(addr)); }}
          style={{ flex: 1, background: "var(--bg2)", border: "1px solid var(--border)", borderRadius: 18, padding: "6px 14px", fontSize: 13, marginInlineStart: 4 }} />
      </div>
      <Webview ref={ref} src={url} style={{ flex: 1, minHeight: 0, background: "#fff" }} />
    </div>
  );
}
