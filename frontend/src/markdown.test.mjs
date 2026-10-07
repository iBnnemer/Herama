// Run with: node --test src/markdown.test.mjs
import test from "node:test";
import assert from "node:assert/strict";
import { parseBlocks, parseInline, splitRow } from "./markdown.ts";

const TABLE = [
  "| الفترة | الدور |",
  "|--------|---------------|",
  "| **2015-2018** | تدخل عسكري |",
  "| **2019** | دعم |",
].join("\n");

test("table with bold cells", () => {
  const [t] = parseBlocks(TABLE);
  assert.equal(t.t, "table");
  assert.equal(t.head.length, 2);
  assert.equal(t.rows.length, 2);
  assert.equal(t.rows[0][0][0].t, "bold");
});

test("heading without space, emoji and bold", () => {
  const [h] = parseBlocks("####1️⃣ **Role**");
  assert.equal(h.t, "heading");
  assert.equal(h.level, 4);
  assert.ok(h.c.some(n => n.t === "bold"));
});

test("hr, paragraph, table keep their order", () => {
  const blocks = parseBlocks(`intro text\n\n---\n\n${TABLE}\n\nafter`);
  assert.deepEqual(blocks.map(b => b.t), ["para", "hr", "table", "para"]);
});

test("a table while streaming is plain text until the separator arrives", () => {
  assert.equal(parseBlocks("| a | b |")[0].t, "para");
  assert.equal(parseBlocks("| a | b |\n|---|---|")[0].t, "table");
});

test("lists and code fences, including an unfinished fence", () => {
  assert.deepEqual(parseBlocks("- a\n- b\n\n1. x\n2. y").map(b => b.t), ["list", "list"]);
  const [c] = parseBlocks("```py\nprint(1)");
  assert.equal(c.t, "code");
  assert.equal(c.v, "print(1)");
});

test("inline: code, link, italic; html stays text", () => {
  assert.deepEqual(parseInline("a `b` c").map(n => n.t), ["text", "code", "text"]);
  assert.equal(parseInline("[x](https://e.com)")[0].t, "link");
  assert.equal(parseInline("javascript:alert(1) [x](javascript:alert(1))").some(n => n.t === "link"), false);
  assert.equal(parseInline("<img src=x onerror=1>")[0].t, "text");
  assert.equal(parseInline("snake_case_name")[0].t, "text");
});

test("splitRow handles escaped pipes", () => {
  assert.deepEqual(splitRow("| a \\| b | c |"), ["a | b", "c"]);
});
