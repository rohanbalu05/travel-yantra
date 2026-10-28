"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { Problem, problemOf } from "@/components/Problem";
import { categoryLabel } from "@/lib/format";
import { kathaLibrary, type LibraryItem } from "@/lib/guide";
import { useI18n } from "@/lib/i18n";
import { usePlanResult } from "@/lib/plan";
import "../guide.css";

const href = (kind: "place" | "city", subject: string) => `/katha/${kind}/?subject=${encodeURIComponent(subject)}`;
// Lengths offered on the web (10 minutes hidden until TY2 says it passes).
const SHOWN = [2, 5];

/** Library items grouped by city, cities and their places together, alphabetical. */
function byCity(items: LibraryItem[]): [string, LibraryItem[]][] {
  const m = new Map<string, LibraryItem[]>();
  for (const x of items) {
    const c = x.city || x.subject;
    m.set(c, [...(m.get(c) ?? []), x]);
  }
  return [...m.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([c, xs]) => [c, xs.sort((a, b) => (a.subject_kind === b.subject_kind ? a.subject.localeCompare(b.subject) : a.subject_kind === "city" ? -1 : 1))]);
}

export default function KathaHome() {
  const plan = usePlanResult();
  const { lang, t } = useI18n();
  const it = plan?.itinerary;
  const stops = it?.days.flatMap((d) => d.stops ?? []) ?? [];
  const [lib, setLib] = useState<{ items?: LibraryItem[]; problem?: { message: string; retryable: boolean } } | null>(null);
  const [run, setRun] = useState(0);

  useEffect(() => {
    const ctl = new AbortController();
    kathaLibrary(lang, ctl.signal)
      .then((r) => setLib({ items: r.items }))
      .catch((e) => !ctl.signal.aborted && setLib({ problem: problemOf(e) }));
    return () => ctl.abort();
  }, [lang, run]);

  const minutes = (x: LibraryItem) => {
    const ls = x.lengths.filter((n) => SHOWN.includes(n));
    return ls.length ? t("{list} min", { list: ls.join(", ") }) : null;
  };

  return (
    <AppShell>
      <div className="k-head">
        <h1 className="page-title">{t("Katha")}</h1>
        <p className="page-sub">{t("The history and legends of a city, a place or a planned day. Every legend is labelled as one, and every history line names its source.")}</p>
      </div>

      {it ? (
        <section aria-labelledby="trip-h">
          <div className="sec-title">
            <h2 className="h2" id="trip-h">{t("For your trip")}</h2>
          </div>
          <div className="kh-grid">
            <Link className="kh-card" href="/katha/day/"><b>{t("Stories for each day")}</b><span>{t("Day Katha")}</span></Link>
            {it.request.destinations.map((c) => (
              <Link key={c} className="kh-card" href={href("city", c)}><b>{c}</b><span>{t("City Katha")}</span></Link>
            ))}
            {stops.map((p) => (
              <Link key={p.id} className="kh-card" href={href("place", p.name)}><b>{p.name}</b><span>{t("Place Katha · {category}", { category: t(categoryLabel(p.category)) })}</span></Link>
            ))}
          </div>
        </section>
      ) : (
        <p className="hint">
          {t("Plan a trip to get a story for each day.")} <Link href="/plan/start/">{t("Plan a trip")}</Link>
        </p>
      )}

      <section aria-labelledby="lib-h">
        <div className="sec-title"><h2 className="h2" id="lib-h">{t("Library")}</h2></div>
        {!lib ? (
          <p className="hint" role="status">{t("Loading")}…</p>
        ) : lib.problem ? (
          <Problem {...lib.problem} onRetry={() => { setLib(null); setRun((r) => r + 1); }} />
        ) : !lib.items!.length ? (
          <p className="hint">{t("No stories in this language yet.")}</p>
        ) : (
          byCity(lib.items!).map(([city, xs]) => (
            <div key={city} className="kh-city">
              <h3 className="h3">{city}</h3>
              <div className="kh-grid">
                {xs.map((x) => (
                  <Link key={x.subject_kind + x.subject} className="kh-card" href={href(x.subject_kind, x.subject)}>
                    <b>{x.subject}</b>
                    <span>{[t(x.subject_kind === "city" ? "City Katha" : "Place Katha"), minutes(x)].filter(Boolean).join(" · ")}</span>
                    {x.has_audio && <span className="badge badge-sea kh-audio">{t("Audio")}</span>}
                  </Link>
                ))}
              </div>
            </div>
          ))
        )}
      </section>
    </AppShell>
  );
}
