/** Decides which tool groups to switch on for a message, so the model never sees all tools at once. */

export const TOOL_GROUPS = ["Files", "Web", "Shell", "Skills", "Memory", "Utilities"] as const;
export type ToolGroup = (typeof TOOL_GROUPS)[number];

// Patterns run on normalized text: lower case, no Arabic diacritics, alef variants merged, ة->ه, ى->ي.
// English words match from their start (so "searching" matches "search"); Arabic words match anywhere (prefixes like و/ف/ب).
const PATTERNS: Record<ToolGroup, RegExp> = {
  Files: new RegExp([
    "\\b(files?|folders?|director(y|ies)|paths?|readme|repo(sitory)?|code|scripts?|program|function|project|workspace)",
    "\\.(py|js|ts|tsx|jsx|json|md|txt|csv|html|css|ya?ml|toml|xml|log|pdf|docx?|xlsx?|png|jpe?g)\\b",
    "(^|[^a-z])[a-z]:(\\\\|/(?!/))", "(^|\\s)\\.{0,2}/[\\w.-]+/",
    "\\b(my (computer|pc|laptop|machine)|drives?|disk|desktop|documents|downloads|home folder)\\b|(^|\\s)~/",
    "ملف|مجلد|دليل|مسار|كود|سكربت|برنامج|دال[هة]|مشروع|ريبو|جهازي|حاسوبي|الكمبيوتر|الحاسوب|الجهاز|سطح المكتب|المستندات|التنزيلات|التحميلات",
  ].join("|"), "i"),
  Web: new RegExp([
    "\\b(search|google|look ?up|browse|online|internet|web|website|url|https?:|www\\.|news|latest|download|weather)",
    "ابحث|بحث|دور على|موقع|رابط|انترنت|اخبار|حمل|نزل|طقس|احدث|اخر",
  ].join("|"), "i"),
  Shell: new RegExp([
    "\\b(run|execute|command|terminal|shell|cmd|powershell|bash|install|pip|npm|git|python|node|build|compile|tests?)\\b",
    "شغل|نفذ|تنفيذ|امر|اوامر|ثبت|تثبيت|تيرمنال|ترمنال|ابني|اختبر",
  ].join("|"), "i"),
  Skills: /\bskills?\b|مهار/i,
  Memory: new RegExp([
    "\\b(remember|forget|recall|memor(y|ies)|don'?t forget|keep in mind)",
    "تذكر|تتذكر|انس|ذاكره|لا تنس|خذ بالك",
  ].join("|"), "i"),
  Utilities: new RegExp([
    "\\b(time|date|today|tomorrow|yesterday|calculate|calc|math|percent|convert|how much|how many|specs?|gpu|cpu|ram|disk)\\b",
    "الوقت|الساعه|التاريخ|اليوم|غدا|احسب|حساب|كم يساوي|حول|مواصفات|كرت|معالج|رام",
  ].join("|"), "i"),
};

export function normalize(text: string): string {
  return text.toLowerCase()
    .replace(/[ً-ٰٟـ]/g, "")
    .replace(/[أإآ]/g, "ا").replace(/ة/g, "ه").replace(/ى/g, "ي");
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

const trim = (p: string) => p.replace(/[\s.,;:!?)\]}،؛؟"'`“”]+$/, "");

/** Absolute file or folder paths written in a message (Windows, Unix or ~/...), quoted or not. */
export function extractPaths(text: string): string[] {
  const found = new Set<string>();
  for (const m of text.matchAll(/["'`“”‘’]([A-Za-z]:(?:\\|\/(?!\/))[^"'`“”‘’\n]+|~?\/[^"'`“”‘’\n]+)["'`“”‘’]/g)) found.add(trim(m[1]));
  for (const m of text.matchAll(/(?<![A-Za-z0-9])([A-Za-z]:(?:\\|\/(?!\/))[^\s"'`<>|?*]+)/g)) found.add(trim(m[1]));
  for (const m of text.matchAll(/(?:^|[\s("'`])((?:~\/[\w.@%+\-]+|\/[\w.@%+\-]+(?:\/[\w.@%+\-]+)+)(?:\/[\w.@%+\-]+)*)/g)) found.add(trim(m[1]));
  const all = [...found].filter(p => p.length > 2);
  return all.filter(p => !all.some(q => q !== p && q.startsWith(p)));  // a quoted path with spaces also yields its first word
}
