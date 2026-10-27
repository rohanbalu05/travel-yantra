"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { NoPlan } from "@/components/NoPlan";
import { Rating } from "@/components/Rating";
import { StopsMap } from "@/components/StopsMap";
import { Trail } from "@/components/Trail";
import type { DayPlan, Itinerary, Mode, ReviseRequest } from "@/lib/contracts";
import { MODE_NAME, clock, dayLabel, duration, inr, weekday } from "@/lib/format";
import { useI18n, type Vars } from "@/lib/i18n";
import { PlanHttpError, savePlanResult, streamRevise, useChoice, usePlanResult } from "@/lib/plan";
import { initialPlanState, planReducer } from "@/lib/planState";
import { againstBudget, dayRows, pickIndex, travellerCount, tripCost } from "@/lib/planView";
import "../plan.css";

// A revise is one day's solve and check; past this the connection has stalled.
const REVISE_TIMEOUT_MS = 90_000;

const PACE_NAME = { relaxed: "gentle pace", balanced: "balanced pace", packed: "packed pace" } as const;

function dayTitle(day: DayPlan, t: (text: string, vars?: Vars) => string): string {
  const names = (day.stops ?? []).map((s) => s.name);
  if (!names.length) return day.notes?.[0] ?? t("Free day");
  return names.length > 2 ? t("{name} and {n} more", { name: names[0], n: names.length - 1 }) : names.join(` ${t("and")} `);
}

function Plan({ it, planId, shareToken }: { it: Itinerary; planId: string | null; shareToken: string | null }) {
  const { t } = useI18n();
  const [sel, setSel] = useState(0);
  const [shared, setShared] = useState<string | null>(null);
  // The link shows the plan only (TY1's GET /trips/{token}), never bookings or names.
  const share = async () => {
    const url = `${window.location.origin}/t/${encodeURIComponent(shareToken!)}/`;
    try {
      await navigator.clipboard.writeText(url);
      setShared(t("Link copied"));
    } catch {
      setShared(url);
    }
  };
  const choice = useChoice() ?? null;
  const [busy, setBusy] = useState<string | null>(null);
  const [said, setSaid] = useState<{ text: string; bad: boolean } | null>(null);
  const live = useRef<AbortController | null>(null);
  useEffect(() => () => live.current?.abort(), []);

  // Revise streams like /plan and ends in done with a new plan; only the day touched changes.
  // `done` is the whole message shown when it works, already translated.
  const revise = async (req: Omit<ReviseRequest, "lang">, done: string) => {
    if (!planId || busy) return;
    setBusy(done);
    setSaid(null);
    const ctl = new AbortController();
    live.current = ctl;
    const timer = setTimeout(() => ctl.abort(), REVISE_TIMEOUT_MS);
    try {
      let s = initialPlanState();
      for await (const ev of streamRevise(planId, { ...req, lang: it.lang ?? "en" }, ctl.signal)) s = planReducer(s, ev);
      if (s.status === "done" && s.itinerary) {
        savePlanResult({ itinerary: s.itinerary, plan_id: s.planId, share_token: s.shareToken });
        setSaid({ text: done, bad: false });
      } else {
        setSaid({ text: t(s.error?.message ?? "The planner stopped before finishing. Try again."), bad: true });
      }
    } catch (e) {
      const text = e instanceof PlanHttpError ? e.message : ctl.signal.aborted ? t("The planner took too long. Try again.") : t("We could not reach the planner. Check your connection.");
      setSaid({ text, bad: true });
    } finally {
      clearTimeout(timer);
      setBusy(null);
    }
  };

  const opts = it.transport ?? [];
  const way = opts[choice !== null && choice < opts.length ? choice : pickIndex(it)];
  const cost = way ? tripCost(it, way) : it.budget.total_inr;
  const vs = againstBudget(it, cost);
  const budget = it.request.constraints?.budget_inr;
  const people = travellerCount(it);
  const pace = it.request.constraints?.pace;
  const day = it.days[sel];
  const rows = day ? dayRows(day, it) : [];
  const travelMin = (day?.legs ?? []).reduce((a, l) => a + l.minutes, 0);
  const travelCost = (day?.legs ?? []).reduce((a, l) => a + l.cost_inr, 0);
  const stay = it.stays?.[0];
  const stayCities = [...new Set((it.stays ?? []).map((s) => s.city))];
  const mode = (m: Mode) => t(MODE_NAME[m]);
  const travellers = t(people > 1 ? "{n} travellers" : "{n} traveller", { n: people });

  return (
    <>
      <div className="it-top">
        <Trail at={4} />
        <div className="it-head">
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <h1 className="page-title">{people > 1 ? t("{dest} with family", { dest: it.request.destinations.join(` ${t("and")} `) }) : it.request.destinations.join(` ${t("and")} `)}</h1>
            <div className="it-meta">
              <span className="badge">{t("{from} to {to}", { from: dayLabel(it.request.start_date), to: dayLabel(it.request.end_date) })}</span>
              {people > 0 && <span className="badge">{pace ? t("{travellers}, {pace}", { travellers, pace: t(PACE_NAME[pace]) }) : travellers}</span>}
              {way && (
                <span className="badge">
                  {stayCities.length === 1
                    ? t("By {mode}, base in {city}", { mode: mode(way.mode).toLowerCase(), city: stayCities[0] })
                    : stayCities.length > 1
                      ? t("By {mode}, stays in {n} cities", { mode: mode(way.mode).toLowerCase(), n: stayCities.length })
                      : t("By {mode}", { mode: mode(way.mode).toLowerCase() })}
                </span>
              )}
              <span className={(it.warnings ?? []).length ? "badge badge-warn" : "badge badge-ok"}>{(it.warnings ?? []).length ? t("{n} to note", { n: it.warnings!.length }) : t("All checks passed")}</span>
              <span className={vs && !vs.ok ? "badge badge-warn" : "badge badge-sea"}>{budget ? t("{total} of {budget}", { total: inr(cost), budget: inr(budget) }) : inr(cost)}</span>
            </div>
          </div>
          <div className="it-actions">
            {shareToken && (
              <button type="button" className="btn btn-quiet btn-sm" onClick={share}>{shared ?? t("Share with family")}</button>
            )}
            <Link className="btn btn-primary btn-sm" href="/book/">{t("Book this plan")}</Link>
          </div>
        </div>
      </div>

      <div className="split">
        <section className="main" aria-label={t("Day by day")}>
          <div className="dtabs" role="tablist" aria-label={t("Days")}>
            {it.days.map((d, i) => (
              <button key={d.date} type="button" role="tab" id={`tab-${i}`} aria-selected={i === sel} aria-controls="day-panel" className={i === sel ? "dtab on" : "dtab"} onClick={() => setSel(i)}>
                <b>{weekday(d.date)} {Number(d.date.slice(8, 10))}</b>
                <span>{dayTitle(d, t)}</span>
              </button>
            ))}
          </div>
          {day && (
            <div id="day-panel" role="tabpanel" aria-labelledby={`tab-${sel}`}>
              <div className="day-sum">
                <span><b>{t("Day")}</b><span>{dayLabel(day.date)}</span></span>
                <span><b>{t("Stops")}</b><span>{(day.stops ?? []).length}</span></span>
                {travelMin > 0 && <span><b>{t("Getting around")}</b><span>{duration(travelMin)}, {inr(travelCost)}</span></span>}
              </div>
              <div>
                {rows.map((r, i) =>
                  r.kind === "stop" ? (
                    <div className="it-row" key={i}>
                      <span className="it-time">{duration(r.place.typical_visit_minutes)}</span>
                      <span className="mk mk-stop">{r.n}</span>
                      <div className="it-body">
                        <b>{r.place.name}</b>
                        <small>{r.place.category[0].toUpperCase() + r.place.category.slice(1)} · {t("about {time} there", { time: duration(r.place.typical_visit_minutes) })}</small>
                      </div>
                      {planId && (
                        <button type="button" className="btn btn-quiet btn-sm it-swap" disabled={!!busy} aria-label={t("Swap {name} for something else", { name: r.place.name })}
                          onClick={() => revise({ intent: "swap_stop", day: day.date, place_id: r.place.id }, t("Done: swapped {name}. The other days are as before, and the checks ran again.", { name: r.place.name }))}>
                          {t("Swap")}
                        </button>
                      )}
                    </div>
                  ) : r.kind === "move" ? (
                    <div className="it-row" key={i}>
                      <span className="it-time">{clock(r.leg.depart)}</span>
                      <span className="mk mk-move"><svg className="ic" viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14" /><path d="M13 6l6 6-6 6" /></svg></span>
                      <div className="it-body">
                        <b>{t("{mode} to {place}", { mode: mode(r.leg.mode), place: r.leg.to })}</b>
                        <small>{duration(r.leg.minutes)} · {inr(r.leg.cost_inr)}</small>
                      </div>
                    </div>
                  ) : (
                    <div className="it-row" key={i}>
                      <span className="it-time">{t("Night")}</span>
                      <span className="mk mk-stay"><svg className="ic" viewBox="0 0 24 24" aria-hidden="true"><path d="M3 18V7" /><path d="M3 14h18v4" /><path d="M3 11h7a2 2 0 0 1 2 2v1" /><path d="M12 14v-2a2 2 0 0 1 2-2h5a2 2 0 0 1 2 2v2" /></svg></span>
                      <div className="it-body"><b>{r.name}</b><small>{t("Your base for the night")}</small></div>
                    </div>
                  ),
                )}
                {rows.length === 0 && <p className="hint">{t("Nothing planned. A day to rest.")}</p>}
              </div>
              {(day.notes ?? []).length > 0 && (
                <div className="panel panel-pad" style={{ marginTop: 16 }}>
                  <h2 className="h3" style={{ marginBottom: 8 }}>{t("Notes for the day")}</h2>
                  <ul className="note-list">{day.notes!.map((n) => <li key={n}>{n}</li>)}</ul>
                </div>
              )}
            </div>
          )}
        </section>

        <aside className="side" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {day && (day.stops ?? []).length > 0 && (
            <StopsMap
              pins={(day.stops ?? []).map((s, i) => ({ id: s.id, label: String(i + 1), name: s.name, lat: s.lat, lng: s.lng, kind: "stop" }))}
              caption={t((day.stops ?? []).length > 1 ? "{date}: {n} stops, numbered in order" : "{date}: {n} stop, numbered in order", { date: dayLabel(day.date), n: (day.stops ?? []).length })}
            />
          )}
          {planId && day && (
            <section className="panel" aria-labelledby="ch-h">
              <div className="panel-head"><h2 className="h3" id="ch-h">{t("Change {day}", { day: weekday(day.date) })}</h2><span className="hint">{t("Only this day is rebuilt")}</span></div>
              <div className="panel-pad" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                <button type="button" className="btn btn-quiet" disabled={!!busy || !(day.stops ?? []).length}
                  onClick={() => revise({ intent: "lighter_day", day: day.date }, t("Done: {day} is lighter. The other days are as before, and the checks ran again.", { day: weekday(day.date) }))}>
                  {t("Make {day} lighter", { day: weekday(day.date) })}
                </button>
                <button type="button" className="btn btn-quiet" disabled={!!busy}
                  onClick={() => revise({ intent: "rain", day: day.date }, t("Done: {day} is planned for rain. The other days are as before, and the checks ran again.", { day: weekday(day.date) }))}>
                  {t("Plan {day} for rain", { day: weekday(day.date) })}
                </button>
                {/* Multi-city: TY1's move_day takes a day from the neighbouring city and re-plans the whole trip. */}
                {it.request.destinations.length > 1 && it.request.destinations.map((c) => (
                  <button key={c} type="button" className="btn btn-quiet" disabled={!!busy}
                    onClick={() => revise({ intent: "move_day", city: c }, t("Done: one more day in {city}. The other days are as before, and the checks ran again.", { city: c }))}>
                    {t("One more day in {city}", { city: c })}
                  </button>
                ))}
                <p role="status" className={said?.bad ? "rev-msg bad" : "rev-msg"} hidden={!busy && !said}>
                  {busy ? t("Rebuilding the day…") : said?.text}
                </p>
              </div>
            </section>
          )}
          <Rating planId={planId} />
          <section className="panel panel-pad" aria-labelledby="b-h">
            <h2 className="h3" id="b-h" style={{ marginBottom: 14 }}>{t("The budget")}</h2>
            <dl className="kv cost">
              <dt>{way ? t("Getting there, {mode}", { mode: mode(way.mode).toLowerCase() }) : t("Getting there")}</dt><dd>{inr(way ? way.total_cost_inr : it.budget.transport_inr)}</dd>
              <dt>{t("Stay")}</dt><dd>{inr(it.budget.stay_inr)}</dd>
              {!!it.budget.food_inr && <><dt>{t("Food")}</dt><dd>{inr(it.budget.food_inr)}</dd></>}
              {!!it.budget.activities_inr && <><dt>{t("Tickets and activities")}</dt><dd>{inr(it.budget.activities_inr)}</dd></>}
              <dt className="tot">{t("Whole trip, estimated")}</dt><dd className="tot">{inr(cost)}</dd>
            </dl>
          </section>
          {stay && (
            <section className="panel panel-pad" aria-labelledby="s-h">
              <h2 className="h3" id="s-h" style={{ marginBottom: 8 }}>{t("Where you stay")}</h2>
              {/* One stay per city on multi-city trips, in the order you reach them. */}
              {[...(it.stays ?? [])].sort((a, b) => a.check_in.localeCompare(b.check_in)).map((s) => (
                <div key={s.name + s.check_in} style={{ marginTop: 8 }}>
                  <p style={{ margin: 0 }}><b>{s.name}</b>, {s.city}</p>
                  <p className="hint" style={{ margin: "4px 0 0" }}>{t("{from} to {to}", { from: dayLabel(s.check_in), to: dayLabel(s.check_out) })} · {t("{price} a night", { price: inr(s.price_per_night_inr) })}</p>
                </div>
              ))}
            </section>
          )}
          {(it.warnings ?? []).length > 0 && (
            <section aria-labelledby="w-h">
              <h2 className="h3" id="w-h" style={{ marginBottom: 8 }}>{t("Good to know")}</h2>
              <ul className="warn-list">{it.warnings!.map((w) => <li key={w}>{w}</li>)}</ul>
            </section>
          )}
          {/* TY1 quotes Wikivoyage or Wikipedia for each city and month; nothing shows when they say nothing. */}
          {(it.season_notes ?? []).length > 0 && (
            <section className="panel panel-pad" aria-labelledby="season-h">
              <h2 className="h3" id="season-h" style={{ marginBottom: 8 }}>{t("Season and weather")}</h2>
              <ul className="note-list">
                {it.season_notes!.map((n) => (
                  <li key={`${n.city}-${n.kind}-${n.text.slice(0, 24)}`}>
                    <b>{n.city}:</b> {n.text}{" "}
                    {/^https?:\/\//i.test(n.source_url) && (
                      <a href={n.source_url} target="_blank" rel="noopener noreferrer">{new URL(n.source_url).hostname.replace(/^www\./, "")}</a>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          )}
        </aside>
      </div>

      <div className="next">
        <div><b>{t("Happy with it? Book it.")}</b><span>{t("Trains, the stay and the cabs. We line them up; you pay the seller directly.")}</span></div>
        <div className="row-wrap">
          <Link className="btn btn-on-dark" href="/plan/options/">{t("Change how you travel")}</Link>
          <Link className="btn btn-primary btn-lg" href="/book/">{t("Book this plan")}</Link>
        </div>
      </div>
    </>
  );
}

export default function ItineraryPage() {
  const res = usePlanResult();
  return <AppShell>{res === undefined ? null : res ? <div><Plan it={res.itinerary} planId={res.plan_id} shareToken={res.share_token ?? null} /></div> : <NoPlan />}</AppShell>;
}
