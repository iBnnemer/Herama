import { useEffect, useRef, useState } from "react";

const Webview = "webview" as unknown as React.ElementType;
const HOME = "https://duckduckgo.com";

function normalize(input: string): string {
  const v = input.trim();
  if (/^https?:\/\//i.test(v)) return v;
  if (/^[\w-]+(\.[\w-]+)+(\/.*)?$/.test(v) || /^localhost(:\d+)?/.test(v)) return `http://${v}`;
  return `https://duckduckgo.com/?q=${encodeURIComponent(v)}`;
}

type WebviewEl = HTMLElement & {
  loadURL: (u: string) => void; goBack: () => void; goForward: () => void; reload: () => void;
};

export default function BrowserPanel() {
  const ref = useRef<WebviewEl | null>(null);
  const [url, setUrl] = useState(HOME);
  const [addr, setAddr] = useState(HOME);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const onNav = (e: Event) => {
      const u = (e as Event & { url?: string }).url;
      if (u) { setUrl(u); setAddr(u); }
    };
    el.addEventListener("did-navigate", onNav);
    el.addEventListener("did-navigate-in-page", onNav);
    return () => {
      el.removeEventListener("did-navigate", onNav);
      el.removeEventListener("did-navigate-in-page", onNav);
    };
  }, []);

  const btn: React.CSSProperties = { padding: "2px 8px", color: "var(--text-mid)", fontSize: 13 };

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0 }}>
      <div style={{ display: "flex", gap: 2, padding: 6, alignItems: "center" }}>
        <button style={btn} onClick={() => ref.current?.goBack()}>{"<"}</button>
        <button style={btn} onClick={() => ref.current?.goForward()}>{">"}</button>
        <button style={btn} onClick={() => ref.current?.reload()}>R</button>
        <input value={addr} onChange={e => setAddr(e.target.value)}
          onKeyDown={e => { if (e.key === "Enter") ref.current?.loadURL(normalize(addr)); }}
          style={{ flex: 1, background: "var(--bg2)", border: "1px solid var(--border)", borderRadius: 6, padding: "4px 10px", fontSize: 12 }} />
      </div>
      <Webview ref={ref} src={url} style={{ flex: 1, minHeight: 0, background: "#fff" }} />
    </div>
  );
}
