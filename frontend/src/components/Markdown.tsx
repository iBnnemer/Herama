import type { CSSProperties, ReactNode } from "react";
import { parseBlocks } from "../markdown";
import type { Block, Inline } from "../markdown";

const cell: CSSProperties = { padding: "8px 14px", verticalAlign: "top", borderTop: "1px solid var(--border)", borderInlineStart: "1px solid var(--border)" };

function inline(nodes: Inline[]): ReactNode[] {
  return nodes.map((n, i) => {
    switch (n.t) {
      case "text": return <span key={i}>{n.v}</span>;
      case "code": return <code key={i} style={{ background: "var(--code-bg)", color: "var(--code-fg)", borderRadius: 6, padding: "2px 6px", fontSize: "0.88em", unicodeBidi: "isolate" }} dir="ltr">{n.v}</code>;
      case "bold": return <strong key={i}>{inline(n.c)}</strong>;
      case "italic": return <em key={i}>{inline(n.c)}</em>;
      case "strike": return <s key={i}>{inline(n.c)}</s>;
      case "link": return <a key={i} href={n.href} target="_blank" rel="noreferrer noopener" style={{ color: "var(--accent)" }}>{inline(n.c)}</a>;
    }
  });
}

function block(b: Block, i: number): ReactNode {
  switch (b.t) {
    case "heading": {
      const size = [0, 22, 19, 17, 15.5, 15, 15][b.level];
      return <div key={i} dir="auto" role="heading" aria-level={b.level} style={{ fontSize: size, fontWeight: 700, margin: "14px 0 6px", textAlign: "start" }}>{inline(b.c)}</div>;
    }
    case "para": return <p key={i} dir="auto" style={{ margin: "0 0 10px", whiteSpace: "pre-wrap", textAlign: "start" }}>{inline(b.c)}</p>;
    case "hr": return <hr key={i} style={{ border: 0, borderTop: "1px solid var(--border)", margin: "14px 0" }} />;
    case "quote": return <blockquote key={i} dir="auto" style={{ margin: "0 0 10px", paddingInlineStart: 12, borderInlineStart: "3px solid var(--border2, var(--border))", color: "var(--text-mid)" }}>{b.c.map(block)}</blockquote>;
    case "code": return (
      <pre key={i} dir="ltr" style={{ margin: "0 0 10px", padding: "10px 12px", background: "var(--bg2)", border: "1px solid var(--border)", borderRadius: 8, overflow: "auto", fontSize: 13, lineHeight: 1.5, whiteSpace: "pre", textAlign: "left" }}>
        <code style={{ color: "var(--text)" }}>{b.v}</code>
      </pre>
    );
    case "list": {
      const Tag = b.ordered ? "ol" : "ul";
      return (
        <Tag key={i} dir="auto" style={{ margin: "0 0 10px", paddingInlineStart: 24 }}>
          {b.items.map((it, k) => <li key={k} style={{ marginInlineStart: it.indent * 18, textAlign: "start" }}>{inline(it.c)}</li>)}
        </Tag>
      );
    }
    case "table": return (
      <div key={i} style={{ margin: "0 0 14px", border: "1px solid var(--border)", borderRadius: 12, overflow: "auto", width: "fit-content", maxWidth: "100%", background: "var(--surface, transparent)" }}>
        <table dir="auto" style={{ borderCollapse: "collapse", fontSize: 14, width: "100%" }}>
          <thead>
            <tr>{b.head.map((h, k) => <th key={k} style={{ ...cell, borderTop: 0, ...(k === 0 ? { borderInlineStart: 0 } : {}), background: "var(--bg2)", fontWeight: 700, textAlign: b.align[k] ?? "start" }}>{inline(h)}</th>)}</tr>
          </thead>
          <tbody>
            {b.rows.map((r, k) => (
              <tr key={k}>{r.map((c, j) => <td key={j} style={{ ...cell, ...(j === 0 ? { borderInlineStart: 0 } : {}), textAlign: b.align[j] ?? "start" }}>{inline(c)}</td>)}</tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }
}

/** Renders model output as formatted text. Nothing from the text is ever interpreted as HTML. */
export default function Markdown({ text }: { text: string }) {
  return <div style={{ whiteSpace: "normal" }}>{parseBlocks(text).map(block)}</div>;
}
