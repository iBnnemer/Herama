/** Long task mode: a goal is split into small checked steps that run one after another, each in a fresh turn. */

export interface Step { title: string; check: string; done?: boolean }

export const MAX_STEPS = 15;

export const LONG_COMMAND = /^\/long\s+([\s\S]+)$/i;

export const planPrompt = (goal: string) =>
  `Split this goal into 3 to ${MAX_STEPS} small, ordered steps that a programmer can do one at a time, each ending in something that can be checked (a file exists, tests pass, a command prints the right result).\n` +
  `Goal: ${goal}\n\n` +
  'Answer with JSON only, no other text: [{"title": "short step", "check": "how to verify it is done"}, ...]';

/** Pull the step list out of a model answer (it may wrap the JSON in text or a code fence, or fall back to a numbered list). */
export function parsePlan(answer: string): Step[] {
  const text = answer.replace(/<think>[\s\S]*?<\/think>/gi, "");
  const start = text.indexOf("[");
  const end = text.lastIndexOf("]");
  if (start >= 0 && end > start) {
    try {
      const raw = JSON.parse(text.slice(start, end + 1)) as unknown;
      if (Array.isArray(raw)) {
        const steps = raw.map(x => typeof x === "string" ? { title: x, check: "" }
          : { title: String((x as Step).title ?? "").trim(), check: String((x as Step).check ?? "").trim() })
          .filter(s => s.title);
        if (steps.length) return steps.slice(0, MAX_STEPS);
      }
    } catch { /* fall through to the numbered list */ }
  }
  const numbered = [...text.matchAll(/^\s*\d+[.)]\s+(.+)$/gm)].map(m => ({ title: m[1].replace(/\*\*/g, "").trim(), check: "" }));
  return numbered.slice(0, MAX_STEPS);
}

export function planMarkdown(goal: string, steps: Step[]): string {
  return `# Plan\n\nGoal: ${goal}\n\n` + steps.map((s, i) => `- [${s.done ? "x" : " "}] ${i + 1}. ${s.title}${s.check ? ` (done when: ${s.check})` : ""}`).join("\n") + "\n";
}

export function stepPrompt(goal: string, steps: Step[], i: number): string {
  const s = steps[i];
  return `Long task: ${goal}\nThe whole plan is in PLAN.md (read it if you need it). Steps already done: ${steps.filter(x => x.done).map(x => x.title).join("; ") || "none"}.\n\n` +
    `Now do step ${i + 1} of ${steps.length} only: ${s.title}\n${s.check ? `It is done when: ${s.check}\n` : ""}` +
    "Do it for real with the tools (write files, run the code, run_checks for tests) and fix what fails. " +
    'When the step is finished reply with "DONE:" and one sentence. If you cannot finish it reply with "BLOCKED:" and the reason.';
}

export type StepResult = "done" | "blocked" | "unclear";

export function stepResult(answer: string): StepResult {
  const t = answer.replace(/<think>[\s\S]*?<\/think>/gi, "").trim();
  if (/\bBLOCKED:/i.test(t)) return "blocked";
  if (/\bDONE:/i.test(t)) return "done";
  return "unclear";
}
