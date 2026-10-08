// Run with: node --test src/loopGuard.test.mjs
import test from "node:test";
import assert from "node:assert/strict";
import { findLoop, makeLoopGuard } from "./loopGuard.ts";

test("finds a repeated sentence and keeps one copy", () => {
  const unit = "The answer is to restart the service and check the logs again. ";
  const text = "Intro text. " + unit.repeat(6);
  const cut = findLoop(text);
  assert.ok(cut > 0 && cut < text.length);
  assert.ok(text.slice(0, cut).endsWith("again. "));
  assert.equal(text.slice(0, cut).split("restart the service").length - 1, 1);
});

test("normal text, tables and dividers are not loops", () => {
  assert.equal(findLoop("A normal answer. ".repeat(1) + "With several different sentences about many things, none repeated at all in this text."), -1);
  assert.equal(findLoop("-".repeat(300)), -1);
  assert.equal(findLoop("| a | b |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n| 5 | 6 |"), -1);
});

test("short phrase repeated many times is a loop", () => {
  assert.ok(findLoop("ok. " + "and then again. ".repeat(12)) > 0);
});

test("guard checks only every few characters", () => {
  const g = makeLoopGuard();
  assert.equal(g("abc"), -1);
});
