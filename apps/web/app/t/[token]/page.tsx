"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { Problem, problemOf } from "@/components/Problem";
import { StopsMap } from "@/components/StopsMap";
import { API_BASE_URL } from "@/lib/api";
import type { Itinerary } from "@/lib/contracts";
import { MODE_NAME, clock, dayLabel, duration, inr, weekday } from "@/lib/format";
import { ApiError, apiJSON } from "@/lib/http";
import { useI18n } from "@/lib/i18n";
import { GOA_ITINERARY, SAMPLE_SHARE_TOKEN } from "@/lib/mockPlan";
import { dayRows } from "@/lib/planView";
import "../../plan/plan.css";

async function sharedTrip(token: string, signal: AbortSignal): Promise<Itinerary> {
  if (!API_BASE_URL) {
    if (token === SAMPLE_SHARE_TOKEN) return GOA_ITINERARY;
    throw new ApiError("trip not found", 404);
  }
  return apiJSON<Itinerary>(`/trips/${encodeURIComponent(token)}`, { signal });
}

function Shared({ it }: { it: Itinerary }) {
  const { t } = useI18n();
  const [sel, setSel] = useState(0);
  const day = it.days[sel];
  const people = it.request.constraints?.travellers?.length ?? 0;
  return (
    <>
      <div className="it-top">
        <p className="badge" style={{ alignSelf: "flex-start", margin: 0 }}>{t("Shared plan, read only")}</p>
        <div className="it-head">
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <h1 className="page-title">{t("{from} to {to}", { from: it.request.origin, to: it.request.destinations.join(` ${t("and")} `) })}</h1>
            <div className="it-meta">
              <span className="badge">{t("{from} to {to}", { from: dayLabel(it.request.start_date), to: dayLabel(it.request.end_date) })}</span>
              {people > 0 && <span className="badge">{t(people > 1 ? "{n} travellers" : "{n} traveller", { n: people })}</span>}
              <span className="badge badge-sea">{t("About {amount} in all", { amount: inr(it.budget.total_inr) })}</span>
            </div>
          </div>
        </div>
        <p className="hint" style={{ margin: 0 }}>{t("This link shows the plan only: no bookings, names or contact details.")}</p>
      </div>
      <div className="split">
        <section className="main" aria-label={t("Day by day")}>
          <div className="dtabs" role="tablist" aria-label={t("Days")}>
            {it.days.map((d, i) => (
              <button key={d.date} type="button" role="tab" aria-selected={i === sel} className={i === sel ? "dtab on" : "dtab"} onClick={() => setSel(i)}>
                <b>{weekday(d.date)} {Number(d.date.slice(8, 10))}</b>
                <span>{(d.stops ?? []).map((s) => s.name).join(", ") || d.notes?.[0] || t("Free day")}</span>
              </button>
            ))}
          </div>
          {day && (
            <div role="tabpanel">
              {dayRows(day, it).map((r, i) => (
                <div className="it-row" key={i}>
                  <span className="it-time">{r.kind === "stop" ? duration(r.place.typical_visit_minutes) : r.kind === "move" ? clock(r.leg.depart) : t("Night")}</span>
                  <span className={r.kind === "stop" ? "mk mk-stop" : r.kind === "move" ? "mk mk-move" : "mk mk-stay"}>{r.kind === "stop" ? r.n : r.kind === "move" ? "→" : "H"}</span>
                  <div className="it-body">
                    <b>{r.kind === "stop" ? r.place.name : r.kind === "move" ? t("{mode} to {place}", { mode: t(MODE_NAME[r.leg.mode]), place: r.leg.to }) : r.name}</b>
                    {r.kind === "stop" && <small>{r.place.category}</small>}
                  </div>
                </div>
              ))}
              {(day.notes ?? []).length > 0 && <ul className="note-list" style={{ marginTop: 12 }}>{day.notes!.map((n) => <li key={n}>{n}</li>)}</ul>}
            </div>
          )}
        </section>
        <aside className="side">
          {day && (day.stops ?? []).length > 0 && (
            <StopsMap pins={(day.stops ?? []).map((s, i) => ({ id: s.id, label: String(i + 1), name: s.name, lat: s.lat, lng: s.lng, kind: "stop" }))} caption={t("{date}, numbered in order", { date: dayLabel(day.date) })} />
          )}
        </aside>
      </div>
      <div className="next">
        <div><b>{t("Plan your own trip")}</b><span>{t("Road, rail and air compared, every stop checked.")}</span></div>
        <Link className="btn btn-primary btn-lg" href="/plan/start/">{t("Plan a trip")}</Link>
      </div>
    </>
  );
}

export default function SharedTripPage() {
  const { token } = useParams<{ token: string }>();
  const { t } = useI18n();
  const [state, setState] = useState<{ it?: Itinerary; problem?: { message: string; retryable: boolean } } | null>(null);
  const [run, setRun] = useState(0);

  useEffect(() => {
    const ctl = new AbortController();
    sharedTrip(token, ctl.signal)
      .then((it) => setState({ it }))
      .catch((e) => {
        if (ctl.signal.aborted) return;
        setState({ problem: e instanceof ApiError && e.status === 404 ? { message: "This shared plan was not found. The link may be wrong or the plan was removed.", retryable: false } : problemOf(e) });
      });
    return () => ctl.abort();
  }, [token, run]);

  return (
    <AppShell>
      <div>
        {!state ? <p className="hint" role="status">{t("Opening the shared plan…")}</p>
          : state.problem ? <Problem {...state.problem} onRetry={() => { setState(null); setRun((r) => r + 1); }} />
          : <Shared it={state.it!} />}
      </div>
    </AppShell>
  );
}
