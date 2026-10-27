import { API_BASE_URL } from "@/lib/api";
import type { GuideAnswer, GuideQuestion, KathaStory, Lang } from "@/lib/contracts";
import { withAuth } from "@/lib/account";
import { ApiError, apiJSON } from "@/lib/http";
import { sampleAnswer, sampleKatha } from "@/lib/samples/guide";

/** TY2's request. For a day, subject is a label ("Day 2, Mysuru") and places lists that day's stops in order. */
export type KathaRequest = { subject_kind: KathaStory["subject_kind"]; subject: string; length_min: 2 | 5 | 10; lang: Lang; places?: string[] };

/** A story plus whether it came from the sample set (shown as a "Sample" tag). */
export type KathaResult = KathaStory & { sample: boolean };

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** POST /guide/ask (TY2). With no API configured, answers from the sample set. */
export async function askGuide(q: GuideQuestion, signal?: AbortSignal, base = API_BASE_URL): Promise<GuideAnswer> {
  if (!base) {
    await wait(350);
    return sampleAnswer(q);
  }
  return withAuth((headers) => apiJSON<GuideAnswer>("/guide/ask", { body: q, signal, base, headers }));
}

/**
 * POST /guide/katha (TY2). A first telling can take up to a minute (several model
 * calls); later ones are cached. Until the route exists on the API (FastAPI's
 * bare "Not Found", or 405), and with no API configured, tells the story from
 * the sample set. TY2's own 404 ("No story for that place yet.") is shown as is.
 */
export async function getKatha(req: KathaRequest, signal?: AbortSignal, base = API_BASE_URL): Promise<KathaResult> {
  const sample = () => ({ ...sampleKatha(req.subject_kind, req.subject, req.length_min, req.lang, req.places), sample: true });
  if (!base) {
    await wait(250);
    return sample();
  }
  try {
    return { ...(await withAuth((headers) => apiJSON<KathaStory>("/guide/katha", { body: req, signal, base, headers }))), sample: false };
  } catch (e) {
    if (e instanceof ApiError && ((e.status === 404 && e.message === "Not Found") || e.status === 405)) return sample();
    throw e;
  }
}

export type CitedPart = { text: string } | { n: number };

/** Splits "a [1] b [2]" into text and marker parts; markers are 1-based indexes into citations. */
export function citedParts(text: string): CitedPart[] {
  const parts: CitedPart[] = [];
  let last = 0;
  for (const m of text.matchAll(/\[(\d+)\]/g)) {
    if (m.index! > last) parts.push({ text: text.slice(last, m.index) });
    parts.push({ n: Number(m[1]) });
    last = m.index! + m[0].length;
  }
  if (last < text.length) parts.push({ text: text.slice(last) });
  return parts;
}
