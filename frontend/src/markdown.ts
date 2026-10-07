/** A small, safe Markdown parser (no HTML is ever interpreted): headings, lists, tables, code, quotes, bold, italic, links. */

export type Inline =
  | { t: "text"; v: string }
  | { t: "code"; v: string }
  | { t: "bold" | "italic" | "strike"; c: Inline[] }
  | { t: "link"; href: string; c: Inline[] };

export type Align = "left" | "center" | "right" | undefined;

export type Block =
  | { t: "heading"; level: number; c: Inline[] }
  | { t: "para"; c: Inline[] }
  | { t: "code"; lang: string; v: string }
  | { t: "quote"; c: Block[] }
  | { t: "hr" }
  | { t: "list"; ordered: boolean; items: { indent: number; c: Inline[] }[] }
  | { t: "table"; head: Inline[][]; align: Align[]; rows: Inline[][][] };

const INLINE = [
  { t: "code" as const, re: /`([^`\n]+)`/ },
  { t: "link" as const, re: /\[([^\]\n]+)\]\((https?:\/\/[^\s)]+)\)/ },
  { t: "bold" as const, re: /\*\*(?=\S)([\s\S]+?)\*\*|__(?=\S)([\s\S]+?)__/ },
  { t: "strike" as const, re: /~~(?=\S)([\s\S]+?)~~/ },
  { t: "italic" as const, re: /\*(?=[^\s*])([^*\n]+?)\*|(?<![\w])_(?=[^\s_])([^_\n]+?)_(?![\w])/ },
];

export function parseInline(s: string): Inline[] {
  const out: Inline[] = [];
  let rest = s;
  while (rest) {
    let best: { t: (typeof INLINE)[number]["t"]; m: RegExpExecArray } | null = null;
    for (const p of INLINE) {
      const m = p.re.exec(rest);
      if (m && (!best || m.index < best.m.index)) best = { t: p.t, m };
    }
    if (!best) { out.push({ t: "text", v: rest }); break; }
    const { t, m } = best;
    if (m.index > 0) out.push({ t: "text", v: rest.slice(0, m.index) });
    if (t === "code") out.push({ t: "code", v: m[1] });
    else if (t === "link") out.push({ t: "link", href: m[2], c: parseInline(m[1]) });
    else out.push({ t, c: parseInline(m[1] ?? m[2]) });
    rest = rest.slice(m.index + m[0].length);
  }
  return out;
}

const FENCE = /^\s*```\s*([\w+-]*)\s*$/;
const HEADING = /^\s{0,3}(#{1,6})\s*(\S.*?)\s*#*\s*$/;
const HR = /^\s*([-*_])(\s*\1){2,}\s*$/;
const LIST = /^(\s*)([-*+]|\d+[.)])\s+(.*)$/;
const QUOTE = /^\s{0,3}>\s?(.*)$/;
const SEP = /^\s*\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)*\|?\s*$/;

export function splitRow(line: string): string[] {
  let t = line.trim();
  if (t.startsWith("|")) t = t.slice(1);
  if (t.endsWith("|") && !t.endsWith("\\|")) t = t.slice(0, -1);
  return t.split(/(?<!\\)\|/).map(c => c.replace(/\\\|/g, "|").trim());
}

const isTableStart = (lines: string[], i: number) =>
  i + 1 < lines.length && lines[i].includes("|") && SEP.test(lines[i + 1]) && lines[i + 1].includes("-") && splitRow(lines[i + 1]).length >= 1
  && (lines[i + 1].includes("|") || splitRow(lines[i]).length === 1);

const startsBlock = (lines: string[], i: number) =>
  FENCE.test(lines[i]) || HEADING.test(lines[i]) || HR.test(lines[i]) || LIST.test(lines[i]) || QUOTE.test(lines[i]) || isTableStart(lines, i);

export function parseBlocks(src: string): Block[] {
  const lines = src.replace(/\r\n?/g, "\n").split("\n");
  const out: Block[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) { i++; continue; }
    const f = FENCE.exec(line);
    if (f) {   // an unfinished fence (still streaming) runs to the end
      const body: string[] = [];
      i++;
      while (i < lines.length && !FENCE.test(lines[i])) body.push(lines[i++]);
      i++;
      out.push({ t: "code", lang: f[1], v: body.join("\n") });
      continue;
    }
    if (isTableStart(lines, i)) {
      const head = splitRow(line);
      const align: Align[] = splitRow(lines[i + 1]).map(c => (c.startsWith(":") && c.endsWith(":") ? "center" : c.endsWith(":") ? "right" : c.startsWith(":") ? "left" : undefined));
      i += 2;
      const rows: Inline[][][] = [];
      while (i < lines.length && lines[i].trim() && lines[i].includes("|")) {
        const cells = splitRow(lines[i++]);
        rows.push(head.map((_, k) => parseInline(cells[k] ?? "")));
      }
      out.push({ t: "table", head: head.map(parseInline), align, rows });
      continue;
    }
    const h = HEADING.exec(line);
    if (h) { out.push({ t: "heading", level: h[1].length, c: parseInline(h[2]) }); i++; continue; }
    if (HR.test(line)) { out.push({ t: "hr" }); i++; continue; }
    if (QUOTE.test(line)) {
      const body: string[] = [];
      while (i < lines.length && QUOTE.test(lines[i])) body.push(QUOTE.exec(lines[i++])![1]);
      out.push({ t: "quote", c: parseBlocks(body.join("\n")) });
      continue;
    }
    const l = LIST.exec(line);
    if (l) {
      const ordered = /\d/.test(l[2]);
      const items: { indent: number; c: Inline[] }[] = [];
      while (i < lines.length) {
        const m = LIST.exec(lines[i]);
        if (!m) break;
        items.push({ indent: Math.min(3, Math.floor(m[1].replace(/\t/g, "  ").length / 2)), c: parseInline(m[3]) });
        i++;
      }
      out.push({ t: "list", ordered, items });
      continue;
    }
    const para: string[] = [line];
    i++;
    while (i < lines.length && lines[i].trim() && !startsBlock(lines, i)) para.push(lines[i++]);
    out.push({ t: "para", c: parseInline(para.join("\n")) });
  }
  return out;
}
