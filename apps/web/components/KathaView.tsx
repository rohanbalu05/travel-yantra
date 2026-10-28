"use client";

import { useEffect, useState, useSyncExternalStore } from "react";
import { Cited, Sources, citationFrom } from "@/components/Cited";
import { KathaPlayer } from "@/components/KathaPlayer";
import { Problem, problemOf } from "@/components/Problem";
import { getKatha, type KathaRequest, type KathaResult } from "@/lib/guide";
import { useI18n } from "@/lib/i18n";

// 10 minutes stays hidden until TY2 says it passes its checks (its /guide/katha answers 404 for it now).
const LENGTHS = [2, 5] as const;
type Length = 2 | 5 | 10;
const LENGTH_KEY = "ty.katha.length";

const noSubscribe = () => () => {};

function savedLength(): Length | null {
  try {
    const n = Number(localStorage.getItem(LENGTH_KEY));
    return (LENGTHS as readonly number[]).includes(n) ? (n as Length) : null;
  } catch {
    return null;
  }
}
// Labels TY2 may add later still show, as plain text with no tag. The English names are dictionary keys.
const LABEL: Record<string, string> = { history: "History", legend: "Legend", disputed: "Disputed" };
const TAG: Record<string, string> = { history: "tag tag-history k-label", legend: "tag tag-legend k-label", disputed: "tag k-label" };
// A first telling runs 4 to 10 model calls (TY2: ~60 s for 2 min, ~200 s for 10 min); past this it has stalled.
// The server still finishes and caches it, so Try again later is instant.
const KATHA_TIMEOUT_MS = 210_000;
// TY2 records audio after the text: on audio_status "pending", ask again every 20 s for a while.
const AUDIO_POLL_MS = 20_000;
const AUDIO_POLLS = 15;

/** The story for one subject with a 2, 5 or 10 minute switch, labelled segments and numbered sources. */
export function KathaView({ req }: { req: Omit<KathaRequest, "length_min" | "lang"> }) {
  const { lang, t } = useI18n();
  // No story is asked for until a length is picked (each first telling is a live model call, QA #113);
  // the last length picked is remembered in this browser.
  const [picked, setPicked] = useState<Length | null>(null);
  const saved = useSyncExternalStore(noSubscribe, savedLength, () => null);
  const length = picked ?? saved;
  const pick = (n: Length) => {
    setPicked(n);
    try {
      localStorage.setItem(LENGTH_KEY, String(n));
    } catch {
      // Storage blocked: picked for this page only.
    }
  };
  const [run, setRun] = useState(0);
  const [result, setResult] = useState<{ key: string; story?: KathaResult; problem?: { message: string; retryable: boolean } } | null>(null);
  // A new language or length is a new request.
  const reqKey = JSON.stringify({ ...req, lang, length_min: length });

  useEffect(() => {
    if (!length) return;
    const ctl = new AbortController();
    const timer = setTimeout(() => ctl.abort("timeout"), KATHA_TIMEOUT_MS);
    getKatha(JSON.parse(reqKey) as KathaRequest, ctl.signal)
      .then((story) => setResult({ key: reqKey, story }))
      .catch((e) => {
        if (ctl.signal.reason === "left") return;
        setResult({ key: reqKey, problem: ctl.signal.reason === "timeout" ? { message: "The story is still being written. It will be ready in a few minutes; try again then.", retryable: true } : problemOf(e) });
      })
      .finally(() => clearTimeout(timer));
    return () => {
      clearTimeout(timer);
      ctl.abort("left");
    };
  }, [reqKey, run, length]);

  // A result for an older request (length switched mid-load) counts as loading.
  const current = result?.key === reqKey ? result : null;
  const story = current?.story;

  // Audio still being recorded: the same request again, quietly, until it is ready (or we give up).
  const [polls, setPolls] = useState(0);
  const pending = story?.audio_status === "pending" && !story.sample;
  useEffect(() => {
    if (!pending || polls >= AUDIO_POLLS) return;
    const ctl = new AbortController();
    const timer = setTimeout(() => {
      getKatha(JSON.parse(reqKey) as KathaRequest, ctl.signal)
        .then((next) => setResult({ key: reqKey, story: next }))
        .catch(() => {})
        .finally(() => setPolls((n) => n + 1));
    }, AUDIO_POLL_MS);
    return () => {
      clearTimeout(timer);
      ctl.abort();
    };
  }, [pending, polls, reqKey]);
  const sources = (story?.sources ?? []).map(citationFrom);

  return (
    <section aria-label={t("Story")}>
      <div className="k-bar">
        <div className="toggle" role="group" aria-label={t("Length")}>
          {LENGTHS.map((n: Length) => (
            <button key={n} type="button" className={n === length ? "on" : undefined} aria-pressed={n === length} onClick={() => pick(n)}>{n} {t("Minutes")}</button>
          ))}
        </div>
        {story?.sample && <span className="badge">{t("Sample story")}</span>}
      </div>
      {!length ? (
        <p className="hint">{t("Pick a length to hear the story.")}</p>
      ) : !current ? (
        <p className="hint" role="status">{t("Writing your story. The first telling can take one to three minutes (longer stories take longer); after that it opens at once.")}</p>
      ) : current.problem ? (
        <Problem {...current.problem} onRetry={() => { setResult(null); setRun((r) => r + 1); }} />
      ) : story && (story.segments ?? []).length ? (
        <div className="k-story">
          {/* Read aloud by TY2 for some stories; none is not an error. The sources stay on screen (they are not read out). */}
          {(story.audio ?? []).length > 0 && <KathaPlayer key={story.audio![0].url} audio={story.audio!} />}
          {pending && !(story.audio ?? []).length && <p className="hint" role="status">{t("The audio is being recorded. It will appear here in a minute or two.")}</p>}
          {story.segments!.map((s, i) => (
            <div key={i} className={s.label === "legend" ? "seg legend" : "seg"}>
              {LABEL[s.label] ? <span className={TAG[s.label]}>{t(LABEL[s.label])}</span> : null}
              <p><Cited text={s.text} id="k-src" count={sources.length} /></p>
            </div>
          ))}
          <Sources id="k-src" items={sources} />
        </div>
      ) : (
        <p className="hint">{story?.text || t("No story yet.")}</p>
      )}
    </section>
  );
}
