// Run with: node --test src/toolRouting.test.mjs
import test from "node:test";
import assert from "node:assert/strict";
import { activeTools, matchGroups } from "./toolRouting.ts";

const cases = [
  ["ابحث عن أحدث نماذج qwen", ["Web"]],
  ["Search for the latest llama.cpp release", ["Web"]],
  ["اقرأ الملف README.md وعدّله", ["Files"]],
  ["شغل الاختبارات في المشروع", ["Files", "Shell"]],
  ["تذكر أنني أفضل الإجابات القصيرة", ["Memory"]],
  ["كم الساعة الآن؟", ["Utilities"]],
  ["hello, how are you?", []],
  ["اكتب لي قصة قصيرة", []],
  ["run my skill for csv cleanup", ["Shell", "Skills"]],
  ["افتح https://example.com", ["Web"]],
  ["see http://x.org/a", ["Web"]],
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
