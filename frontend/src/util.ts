export const rid = (): string => Date.now().toString(36) + Math.random().toString(36).slice(2, 6);

import type { Attachment } from "./types";

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
