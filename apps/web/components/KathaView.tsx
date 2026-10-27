"use client";

import { useEffect, useState } from "react";
import { Cited, Sources, citationFrom } from "@/components/Cited";
import { Problem, problemOf } from "@/components/Problem";
import { getKatha, type KathaRequest, type KathaResult } from "@/lib/guide";
import { useI18n } from "@/lib/i18n";

const LENGTHS = [2, 5, 10] as const;
// Labels TY2 may add later still show, as plain text with no tag. The English names are dictionary keys.
const LABEL: Record<string, string> = { history: "History", legend: "Legend", disputed: "Disputed" };
const TAG: Record<string, string> = { history: "tag tag-history k-label", legend: "tag tag-legend k-label", disputed: "tag k-label" };
// A first telling runs 4 to 10 model calls (TY2: ~60 s for 2 min, ~200 s for 10 min); past this it has stalled.
// The server still finishes and caches it, so Try again later is instant.
const KATHA_TIMEOUT_MS = 210_000;

/** The story for one subject with a 2, 5 or 10 minute switch, labelled segments and numbered sources. */
export function KathaView({ req }: { req: Omit<KathaRequest, "length_min" | "lang"> }) {
  const { lang, t } = useI18n();
  const [length, setLength] = useState<2 | 5 | 10>(5);
  const [run, setRun] = useState(0);
  const [result, setResult] = useState<{ key: string; story?: KathaResult; problem?: { message: string; retryable: boolean } } | null>(null);
  // A new language or length is a new request.
  const reqKey = JSON.stringify({ ...req, lang, length_min: length });

  useEffect(() => {
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
  }, [reqKey, run]);

  // A result for an older request (length switched mid-load) counts as loading.
  const current = result?.key === reqKey ? result : null;
  const story = current?.story;
  const sources = (story?.sources ?? []).map(citationFrom);

  return (
    <section aria-label={t("Story")}>
      <div className="k-bar">
        <div className="toggle" role="group" aria-label={t("Length")}>
          {LENGTHS.map((n) => (
            <button key={n} type="button" className={n === length ? "on" : undefined} aria-pressed={n === length} onClick={() => setLength(n)}>{n} {t("Minutes")}</button>
          ))}
        </div>
        {story?.sample && <span className="badge">{t("Sample story")}</span>}
      </div>
      {!current ? (
        <p className="hint" role="status">{t("Writing your story. The first telling can take one to three minutes (longer stories take longer); after that it opens at once.")}</p>
      ) : current.problem ? (
        <Problem {...current.problem} onRetry={() => { setResult(null); setRun((r) => r + 1); }} />
      ) : story && (story.segments ?? []).length ? (
        <div className="k-story">
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
