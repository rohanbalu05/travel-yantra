import type { ChatEvent } from "./chatClient";

export type Line =
  | { id: number; role: "user"; text: string }
  | { id: number; role: "heard"; text: string }
  | { id: number; role: "bot"; text: string }
  | { id: number; role: "note"; text: string }
  | { id: number; role: "error"; text: string }
  | { id: number; role: "audio"; url: string; text?: string }
  | { id: number; role: "updated" };

export type ChatState = { lines: Line[]; chips: string[]; busy: boolean; next: number };

export const EMPTY: ChatState = { lines: [], chips: [], busy: false, next: 1 };
const MAX_LINES = 200;

const add = (s: ChatState, line: Omit<Line, "id"> | Line): ChatState => ({
  ...s,
  lines: [...s.lines, { ...line, id: s.next } as Line].slice(-MAX_LINES),
  next: s.next + 1,
});

export type Action = { kind: "sent"; text: string } | { kind: "event"; event: ChatEvent } | { kind: "failed"; text: string };

/** The conversation on screen. A note ("Working on your plan") is replaced by the reply that follows it. */
export function reduce(s: ChatState, a: Action): ChatState {
  if (a.kind === "sent") return { ...add(s, { role: "user", text: a.text }), chips: [], busy: true };
  if (a.kind === "failed") return { ...add(dropNotes(s), { role: "error", text: a.text }), busy: false };
  const e = a.event;
  switch (e.type) {
    case "heard":
      return e.text ? add(s, { role: "heard", text: e.text }) : s;
    case "note":
      return e.text ? add(dropNotes(s), { role: "note", text: e.text }) : s;
    case "text":
      return e.text ? add(dropNotes(s), { role: "bot", text: e.text }) : s;
    case "error":
      return add(dropNotes(s), { role: "error", text: e.text ?? "" });
    case "chips":
      return { ...s, chips: (e.chips ?? []).slice(0, 6) };
    case "audio":
      return e.url ? add(s, { role: "audio", url: e.url, text: e.text }) : s;
    case "plan":
      return add(s, { role: "updated" });
    case "done":
      return { ...dropNotes(s), busy: false };
    default:
      return s;
  }
}

const dropNotes = (s: ChatState): ChatState => ({ ...s, lines: s.lines.filter((l) => l.role !== "note") });

/** Bare URLs and [n] source lines in a reply, split out so they can be links. */
export function pieces(text: string): { text: string; href?: string }[] {
  const out: { text: string; href?: string }[] = [];
  const re = /https?:\/\/[^\s<>"')]+/g;
  let last = 0;
  for (const m of text.matchAll(re)) {
    if (m.index > last) out.push({ text: text.slice(last, m.index) });
    out.push({ text: m[0], href: m[0] });
    last = m.index + m[0].length;
  }
  if (last < text.length) out.push({ text: text.slice(last) });
  return out;
}
