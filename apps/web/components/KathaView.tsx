"use client";

import { useEffect, useState } from "react";
import { Cited, Sources, citationFrom } from "@/components/Cited";
import { Problem, problemOf } from "@/components/Problem";
import { getKatha, type KathaRequest, type KathaResult } from "@/lib/guide";

const LENGTHS = [2, 5, 10] as const;
// Labels TY2 may add later still show, as plain text with no tag.
const LABEL: Record<string, string> = { history: "History", legend: "Legend", disputed: "Disputed" };
const TAG: Record<string, string> = { history: "tag tag-history k-label", legend: "tag tag-legend k-label", disputed: "tag k-label" };
// A first telling runs several model calls; past this the connection has stalled.
const KATHA_TIMEOUT_MS = 90_000;

/** The story for one subject with a 2, 5 or 10 minute switch, labelled segments and numbered sources. */
export function KathaView({ req }: { req: Omit<KathaRequest, "length_min"> }) {
  const [length, setLength] = useState<2 | 5 | 10>(5);
  const [run, setRun] = useState(0);
  const [result, setResult] = useState<{ key: string; story?: KathaResult; problem?: { message: string; retryable: boolean } } | null>(null);
  const reqKey = JSON.stringify({ ...req, length_min: length });

  useEffect(() => {
    const ctl = new AbortController();
    const timer = setTimeout(() => ctl.abort("timeout"), KATHA_TIMEOUT_MS);
    getKatha(JSON.parse(reqKey) as KathaRequest, ctl.signal)
      .then((story) => setResult({ key: reqKey, story }))
      .catch((e) => {
        if (ctl.signal.reason === "left") return;
        setResult({ key: reqKey, problem: ctl.signal.reason === "timeout" ? { message: "The story took too long. Try again.", retryable: true } : problemOf(e) });
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
    <section aria-label="Story">
      <div className="k-bar">
        <div className="toggle" role="group" aria-label="Length">
          {LENGTHS.map((n) => (
            <button key={n} type="button" className={n === length ? "on" : undefined} aria-pressed={n === length} onClick={() => setLength(n)}>{n} min</button>
          ))}
        </div>
        {story?.sample && <span className="badge">Sample story</span>}
      </div>
      {!current ? (
        <p className="hint" role="status">Writing your story. The first telling of a place can take up to a minute.</p>
      ) : current.problem ? (
        <Problem {...current.problem} onRetry={() => { setResult(null); setRun((r) => r + 1); }} />
      ) : story && (story.segments ?? []).length ? (
        <div className="k-story">
          {story.segments!.map((s, i) => (
            <div key={i} className={s.label === "legend" ? "seg legend" : "seg"}>
              {LABEL[s.label] ? <span className={TAG[s.label]}>{LABEL[s.label]}</span> : null}
              <p><Cited text={s.text} id="k-src" count={sources.length} /></p>
            </div>
          ))}
          <Sources id="k-src" items={sources} />
        </div>
      ) : (
        <p className="hint">{story?.text || "No story yet."}</p>
      )}
    </section>
  );
}
