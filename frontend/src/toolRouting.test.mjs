// Run with: node --test src/toolRouting.test.mjs
import test from "node:test";
import assert from "node:assert/strict";
import { activeTools, extractPaths, matchGroups } from "./toolRouting.ts";

const cases = [
  ["\u0627\u0628\u062d\u062b \u0639\u0646 \u0623\u062d\u062f\u062b \u0646\u0645\u0627\u0630\u062c qwen", ["Web"]],
  ["Search for the latest llama.cpp release", ["Web"]],
  ["\u0627\u0642\u0631\u0623 \u0627\u0644\u0645\u0644\u0641 README.md \u0648\u0639\u062f\u0651\u0644\u0647", ["Files"]],
  ["\u0634\u063a\u0644 \u0627\u0644\u0627\u062e\u062a\u0628\u0627\u0631\u0627\u062a \u0641\u064a \u0627\u0644\u0645\u0634\u0631\u0648\u0639", ["Files", "Shell"]],
  ["\u062a\u0630\u0643\u0631 \u0623\u0646\u0646\u064a \u0623\u0641\u0636\u0644 \u0627\u0644\u0625\u062c\u0627\u0628\u0627\u062a \u0627\u0644\u0642\u0635\u064a\u0631\u0629", ["Memory"]],
  ["\u0643\u0645 \u0627\u0644\u0633\u0627\u0639\u0629 \u0627\u0644\u0622\u0646\u061f", ["Utilities"]],
  ["hello, how are you?", []],
  ["\u0627\u0643\u062a\u0628 \u0644\u064a \u0642\u0635\u0629 \u0642\u0635\u064a\u0631\u0629", []],
  ["run my skill for csv cleanup", ["Shell", "Skills"]],
  ["\u0627\u0641\u062a\u062d https://example.com", ["Web"]],
  ["see http://x.org/a", ["Web"]],
  ["\u0627\u0628\u062d\u062b \u0641\u064a \u062c\u0647\u0627\u0632\u064a \u0639\u0646 \u0641\u0627\u062a\u0648\u0631\u0629 \u0627\u0644\u0643\u0647\u0631\u0628\u0627\u0621", ["Files", "Web"]], ["\u0645\u0627 \u0645\u0648\u0627\u0635\u0641\u0627\u062a \u062c\u0647\u0627\u0632\u064a", ["Files", "Utilities"]],
  ["find my tax pdf on my computer", ["Files"]],
  ["commit my changes and push", ["Git"]],
  ["start the dev server on port 3000", ["Shell"]],
];

for (const [text, want] of cases) {
  test(`groups for: ${text}`, () => assert.deepEqual(matchGroups(text), want));
}

test("only active groups plus the small always-on tools are offered", () => {
  const all = [
    { name: "read_file", group: "Files", kind: "read" }, { name: "web_search", group: "Web", kind: "net" },
    { name: "ask_user", group: "Utilities", kind: "ui" }, { name: "update_plan", group: "Utilities", kind: "ui" },
  ];
  assert.deepEqual(activeTools(all, new Set(["Web"])).map(t => t.name), ["web_search", "ask_user", "update_plan"]);
  assert.deepEqual(activeTools(all, new Set()).map(t => t.name), ["ask_user"]);
});

test("paths are found in messages", () => {
  assert.deepEqual(extractPaths("\u062d\u0644\u0644 \u0627\u0644\u0645\u0644\u0641 C:\\Users\\Ali\\Documents\\report.docx \u0645\u0646 \u0641\u0636\u0644\u0643."), ["C:\\Users\\Ali\\Documents\\report.docx"]);
  assert.deepEqual(extractPaths('\u0627\u0642\u0631\u0623 "D:\\My Files\\notes 2026.txt" \u0627\u0644\u0622\u0646'), ["D:\\My Files\\notes 2026.txt"]);
  assert.deepEqual(extractPaths("look at /home/me/project/src and ~/notes/todo.md, then"), ["/home/me/project/src", "~/notes/todo.md"]);
  assert.deepEqual(extractPaths("see https://example.com/a/b and http://x.org/y"), []);
  assert.deepEqual(extractPaths("use /help or and/or"), []);
  assert.deepEqual(extractPaths("C:/Users/me/a.txt"), ["C:/Users/me/a.txt"]);
});
