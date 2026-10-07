/** Decides which tool groups to switch on for a message, so the model never sees all tools at once. */

export const TOOL_GROUPS = ["Files", "Web", "Shell", "Skills", "Memory", "Agents", "Utilities"] as const;
export type ToolGroup = (typeof TOOL_GROUPS)[number];

// Patterns run on normalized text: lower case, no Arabic diacritics, alef variants merged, ta marbuta and alef maqsura folded.
// English words match from their start (so "searching" matches "search"); Arabic words match anywhere (so attached prefixes still match).
const PATTERNS: Record<ToolGroup, RegExp> = {
  Files: new RegExp([
    "\\b(files?|folders?|director(y|ies)|paths?|readme|repo(sitory)?|code|scripts?|program|function|project|workspace)",
    "\\.(py|js|ts|tsx|jsx|json|md|txt|csv|html|css|ya?ml|toml|xml|log|pdf|docx?|xlsx?|png|jpe?g)\\b",
    "(^|[^a-z])[a-z]:(\\\\|/(?!/))", "(^|\\s)\\.{0,2}/[\\w.-]+/",
    "\\b(my (computer|pc|laptop|machine)|drives?|disk|desktop|documents|downloads|home folder)\\b|(^|\\s)~/",
    "\u0645\u0644\u0641|\u0645\u062c\u0644\u062f|\u062f\u0644\u064a\u0644|\u0645\u0633\u0627\u0631|\u0643\u0648\u062f|\u0633\u0643\u0631\u0628\u062a|\u0628\u0631\u0646\u0627\u0645\u062c|\u062f\u0627\u0644[\u0647\u0629]|\u0645\u0634\u0631\u0648\u0639|\u0631\u064a\u0628\u0648|\u062c\u0647\u0627\u0632\u064a|\u062d\u0627\u0633\u0648\u0628\u064a|\u0627\u0644\u0643\u0645\u0628\u064a\u0648\u062a\u0631|\u0627\u0644\u062d\u0627\u0633\u0648\u0628|\u0627\u0644\u062c\u0647\u0627\u0632|\u0633\u0637\u062d \u0627\u0644\u0645\u0643\u062a\u0628|\u0627\u0644\u0645\u0633\u062a\u0646\u062f\u0627\u062a|\u0627\u0644\u062a\u0646\u0632\u064a\u0644\u0627\u062a|\u0627\u0644\u062a\u062d\u0645\u064a\u0644\u0627\u062a",
  ].join("|"), "i"),
  Web: new RegExp([
    "\\b(search|google|look ?up|browse|online|internet|web|website|url|https?:|www\\.|news|latest|download|weather)",
    "\u0627\u0628\u062d\u062b|\u0628\u062d\u062b|\u062f\u0648\u0631 \u0639\u0644\u0649|\u0645\u0648\u0642\u0639|\u0631\u0627\u0628\u0637|\u0627\u0646\u062a\u0631\u0646\u062a|\u0627\u062e\u0628\u0627\u0631|\u062d\u0645\u0644|\u0646\u0632\u0644|\u0637\u0642\u0633|\u0627\u062d\u062f\u062b|\u0627\u062e\u0631",
  ].join("|"), "i"),
  Shell: new RegExp([
    "\\b(run|execute|command|terminal|shell|cmd|powershell|bash|install|pip|npm|git|python|node|build|compile|tests?)\\b",
    "\u0634\u063a\u0644|\u0646\u0641\u0630|\u062a\u0646\u0641\u064a\u0630|\u0627\u0645\u0631|\u0627\u0648\u0627\u0645\u0631|\u062b\u0628\u062a|\u062a\u062b\u0628\u064a\u062a|\u062a\u064a\u0631\u0645\u0646\u0627\u0644|\u062a\u0631\u0645\u0646\u0627\u0644|\u0627\u0628\u0646\u064a|\u0627\u062e\u062a\u0628\u0631",
  ].join("|"), "i"),
  Skills: /\bskills?\b|\u0645\u0647\u0627\u0631/i,
  Memory: new RegExp([
    "\\b(remember|forget|recall|memor(y|ies)|don'?t forget|keep in mind)",
    "\u062a\u0630\u0643\u0631|\u062a\u062a\u0630\u0643\u0631|\u0627\u0646\u0633|\u0630\u0627\u0643\u0631\u0647|\u0644\u0627 \u062a\u0646\u0633|\u062e\u0630 \u0628\u0627\u0644\u0643",
  ].join("|"), "i"),
  Agents: new RegExp([
    "\\b(agents?|delegate|collaborat\\w*|teammates?|ask (the|another|other) )",
    "\u0648\u0643\u064a\u0644|\u0648\u0643\u0644\u0627\u0621|\u0641\u0631\u064a\u0642",
  ].join("|"), "i"),
  Utilities: new RegExp([
    "\\b(time|date|today|tomorrow|yesterday|calculate|calc|math|percent|convert|how much|how many|specs?|gpu|cpu|ram|disk)\\b",
    "\u0627\u0644\u0648\u0642\u062a|\u0627\u0644\u0633\u0627\u0639\u0647|\u0627\u0644\u062a\u0627\u0631\u064a\u062e|\u0627\u0644\u064a\u0648\u0645|\u063a\u062f\u0627|\u0627\u062d\u0633\u0628|\u062d\u0633\u0627\u0628|\u0643\u0645 \u064a\u0633\u0627\u0648\u064a|\u062d\u0648\u0644|\u0645\u0648\u0627\u0635\u0641\u0627\u062a|\u0643\u0631\u062a|\u0645\u0639\u0627\u0644\u062c|\u0631\u0627\u0645",
  ].join("|"), "i"),
};

export function normalize(text: string): string {
  return text.toLowerCase()
    .replace(/[\u064b-\u065f\u0670\u0640]/g, "")
    .replace(/[\u0623\u0625\u0622]/g, "\u0627").replace(/\u0629/g, "\u0647").replace(/\u0649/g, "\u064a");
}

/** Groups whose keywords appear in `text`. */
export function matchGroups(text: string): ToolGroup[] {
  const t = normalize(text);
  return TOOL_GROUPS.filter(g => PATTERNS[g].test(t));
}

/** Groups that make a step-by-step plan worth keeping. */
export const PLANNING_GROUPS: ToolGroup[] = ["Files", "Web", "Shell", "Skills"];

/** Names of the tools to offer: those of the active groups, plus the small always-on ones. */
export function activeTools<T extends { name: string; group: string; kind: string }>(all: T[], active: Set<string>): T[] {
  const planning = PLANNING_GROUPS.some(g => active.has(g));
  return all.filter(t => t.kind === "ui" ? (t.name !== "update_plan" || planning) : active.has(t.group));
}

const trim = (p: string) => p.replace(/[\s.,;:!?)\]}\u060c\u061b\u061f"'`“”]+$/, "");

/** Absolute file or folder paths written in a message (Windows, Unix or ~/...), quoted or not. */
export function extractPaths(text: string): string[] {
  const found = new Set<string>();
  for (const m of text.matchAll(/["'`“”‘’]([A-Za-z]:(?:\\|\/(?!\/))[^"'`“”‘’\n]+|~?\/[^"'`“”‘’\n]+)["'`“”‘’]/g)) found.add(trim(m[1]));
  for (const m of text.matchAll(/(?<![A-Za-z0-9])([A-Za-z]:(?:\\|\/(?!\/))[^\s"'`<>|?*]+)/g)) found.add(trim(m[1]));
  for (const m of text.matchAll(/(?:^|[\s("'`])((?:~\/[\w.@%+\-]+|\/[\w.@%+\-]+(?:\/[\w.@%+\-]+)+)(?:\/[\w.@%+\-]+)*)/g)) found.add(trim(m[1]));
  const all = [...found].filter(p => p.length > 2);
  return all.filter(p => !all.some(q => q !== p && q.startsWith(p)));  // a quoted path with spaces also yields its first word
}
