// Run with: node --test src/longTask.test.mjs
import test from "node:test";
import assert from "node:assert/strict";
import { parsePlan, planMarkdown, stepPrompt, stepResult, LONG_COMMAND } from "./longTask.ts";

test("parsePlan reads JSON inside text or a fence", () => {
  const a = 'Here:\n```json\n[{"title":"Create app","check":"file exists"},{"title":"Add tests","check":"tests pass"}]\n```';
  assert.deepEqual(parsePlan(a).map(s => s.title), ["Create app", "Add tests"]);
  assert.equal(parsePlan('["a","b"]').length, 2);
});

test("parsePlan falls back to a numbered list and caps the length", () => {
  assert.deepEqual(parsePlan("1. **First**\n2) Second").map(s => s.title), ["First", "Second"]);
  const many = JSON.stringify(Array.from({ length: 40 }, (_, i) => ({ title: `s${i}` })));
  assert.equal(parsePlan(many).length, 15);
  assert.deepEqual(parsePlan("no plan here"), []);
});

test("plan file and step prompt", () => {
  const steps = [{ title: "A", check: "x", done: true }, { title: "B", check: "" }];
  const md = planMarkdown("goal", steps);
  assert.ok(md.includes("- [x] 1. A (done when: x)") && md.includes("- [ ] 2. B"));
  assert.ok(stepPrompt("goal", steps, 1).includes("step 2 of 2") && stepPrompt("goal", steps, 1).includes("A"));
});

test("step result and command", () => {
  assert.equal(stepResult("DONE: wrote it"), "done");
  assert.equal(stepResult("<think>DONE:</think>BLOCKED: no network"), "blocked");
  assert.equal(stepResult("I did stuff"), "unclear");
  assert.equal(LONG_COMMAND.exec("/long build a todo app")[1], "build a todo app");
  assert.equal(LONG_COMMAND.exec("/longer"), null);
});
