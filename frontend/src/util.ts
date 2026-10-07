export const rid = (): string => Date.now().toString(36) + Math.random().toString(36).slice(2, 6);

import type { Attachment, Project, ProjectFile } from "./types";

const MAX_IMAGE_EDGE = 1280;
const MAX_TEXT_BYTES = 300_000;

function downscale(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      const k = Math.min(1, MAX_IMAGE_EDGE / Math.max(img.width, img.height));
      const c = document.createElement("canvas");
      c.width = Math.round(img.width * k);
      c.height = Math.round(img.height * k);
      c.getContext("2d")!.drawImage(img, 0, 0, c.width, c.height);
      URL.revokeObjectURL(url);
      resolve(c.toDataURL("image/jpeg", 0.85));
    };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("cannot read image")); };
    img.src = url;
  });
}

export async function readAttachment(file: File): Promise<Attachment | string> {
  const name = file.name || "pasted";
  if (file.type.startsWith("image/")) {
    try { return { id: rid(), name, kind: "image", dataUrl: await downscale(file) }; }
    catch { return `${name}: could not read this image`; }
  }
  if (file.size > MAX_TEXT_BYTES) return `${name}: file is too large (limit ${MAX_TEXT_BYTES / 1000} KB)`;
  const text = await file.text();
  if (text.includes("\u0000")) return `${name}: binary files are not supported`;
  return { id: rid(), name, kind: "file", text };
}

/** Split model output into its reasoning (inside <think> tags) and the visible answer. */
export function splitThink(text: string): { think: string; answer: string; open: boolean } {
  if (!text.startsWith("<think>")) return { think: "", answer: text, open: false };
  const end = text.indexOf("</think>");
  if (end < 0) return { think: text.slice(7), answer: "", open: true };
  return { think: text.slice(7, end).trim(), answer: text.slice(end + 8).replace(/^\s+/, ""), open: false };
}

export async function readProjectFile(file: File): Promise<ProjectFile | string> {
  if (file.type.startsWith("image/")) return `${file.name}: images cannot be used as project knowledge`;
  const r = await readAttachment(file);
  return typeof r === "string" ? r : { id: rid(), name: r.name, size: file.size, text: r.text ?? "" };
}

/** System text describing the project: its instructions and as many knowledge files as fit in ~40% of the context. */
export function projectContext(project: Project | undefined, ctx: number): string {
  if (!project) return "";
  const parts = [`You are working inside the project "${project.name}".${project.description ? ` ${project.description}` : ""}`];
  if (project.instructions?.trim()) parts.push(`Project instructions:\n${project.instructions.trim()}`);
  let room = Math.floor(ctx * 0.4 * 2.5) - parts.join("\n\n").length;
  const files: string[] = [];
  const skipped: string[] = [];
  for (const f of project.files ?? []) {
    const head = `### ${f.name}\n`;
    if (room < head.length + 400) { skipped.push(f.name); continue; }
    const body = f.text.length + head.length <= room ? f.text : `${f.text.slice(0, room - head.length - 20)}\n[truncated]`;
    files.push(head + body);
    room -= head.length + body.length;
  }
  if (files.length) parts.push(`Project files:\n\n${files.join("\n\n")}`);
  if (skipped.length) parts.push(`Files not included because the context is full: ${skipped.join(", ")}`);
  return parts.join("\n\n");
}
