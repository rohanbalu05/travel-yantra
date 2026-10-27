"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { NoPlan } from "@/components/NoPlan";
import { StopsMap } from "@/components/StopsMap";
import { Trail } from "@/components/Trail";
import type { DayPlan, Itinerary, ReviseRequest } from "@/lib/contracts";
import { MODE_NAME, clock, dayLabel, duration, inr, weekday } from "@/lib/format";
import { PlanHttpError, savePlanResult, streamRevise, useChoice, usePlanResult } from "@/lib/plan";
import { initialPlanState, planReducer } from "@/lib/planState";
import { againstBudget, dayRows, pickIndex, travellerCount, tripCost } from "@/lib/planView";
import "../plan.css";

// A revise is one day's solve and check; past this the connection has stalled.
const REVISE_TIMEOUT_MS = 90_000;

const PACE_NAME = { relaxed: "gentle pace", balanced: "balanced pace", packed: "packed pace" } as const;

function dayTitle(day: DayPlan): string {
  const names = (day.stops ?? []).map((s) => s.name);
  if (!names.length) return day.notes?.[0] ?? "Free day";
  return names.length > 2 ? `${names[0]} and ${names.length - 1} more` : names.join(" and ");
}

function Plan({ it, planId, shareToken }: { it: Itinerary; planId: string | null; shareToken: string | null }) {
  const [sel, setSel] = useState(0);
  const [shared, setShared] = useState<string | null>(null);
  // The link shows the plan only (TY1's GET /trips/{token}), never bookings or names.
  const share = async () => {
    const url = `${window.location.origin}/t/${encodeURIComponent(shareToken!)}/`;
    try {
      await navigator.clipboard.writeText(url);
      setShared("Link copied");
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
  const revise = async (req: Omit<ReviseRequest, "lang">, label: string) => {
    if (!planId || busy) return;
    setBusy(label);
    setSaid(null);
    const ctl = new AbortController();
    live.current = ctl;
    const timer = setTimeout(() => ctl.abort(), REVISE_TIMEOUT_MS);
    try {
      let s = initialPlanState();
      for await (const ev of streamRevise(planId, { ...req, lang: it.lang ?? "en" }, ctl.signal)) s = planReducer(s, ev);
      if (s.status === "done" && s.itinerary) {
        savePlanResult({ itinerary: s.itinerary, plan_id: s.planId, share_token: s.shareToken });
        setSaid({ text: `Done: ${label}. The other days are as before, and the checks ran again.`, bad: false });
      } else {
        setSaid({ text: s.error?.message ?? "The planner stopped before finishing. Try again.", bad: true });
      }
    } catch (e) {
      const text = e instanceof PlanHttpError ? e.message : ctl.signal.aborted ? "The planner took too long. Try again." : "We could not reach the planner. Check your connection.";
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

  return (
    <>
      <div className="it-top">
        <Trail at={4} />
        <div className="it-head">
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <h1 className="page-title">{it.request.destinations.join(" and ")}{people > 1 ? " with family" : ""}</h1>
            <div className="it-meta">
              <span className="badge">{dayLabel(it.request.start_date)} to {dayLabel(it.request.end_date)}</span>
              {people > 0 && <span className="badge">{people} traveller{people > 1 ? "s" : ""}{pace ? `, ${PACE_NAME[pace]}` : ""}</span>}
              {way && <span className="badge">By {MODE_NAME[way.mode].toLowerCase()}{stay ? `, base in ${stay.city}` : ""}</span>}
              <span className={(it.warnings ?? []).length ? "badge badge-warn" : "badge badge-ok"}>{(it.warnings ?? []).length ? `${it.warnings!.length} to note` : "All checks passed"}</span>
              <span className={vs && !vs.ok ? "badge badge-warn" : "badge badge-sea"}>{inr(cost)}{budget ? ` of ${inr(budget)}` : ""}</span>
            </div>
          </div>
          <div className="it-actions">
            {shareToken && (
              <button type="button" className="btn btn-quiet btn-sm" onClick={share}>{shared ?? "Share with family"}</button>
            )}
            <Link className="btn btn-primary btn-sm" href="/book/">Book this plan</Link>
          </div>
        </div>
      </div>

      <div className="split">
        <section className="main" aria-label="Day by day">
          <div className="dtabs" role="tablist" aria-label="Days">
            {it.days.map((d, i) => (
              <button key={d.date} type="button" role="tab" id={`tab-${i}`} aria-selected={i === sel} aria-controls="day-panel" className={i === sel ? "dtab on" : "dtab"} onClick={() => setSel(i)}>
                <b>{weekday(d.date)} {Number(d.date.slice(8, 10))}</b>
                <span>{dayTitle(d)}</span>
              </button>
            ))}
          </div>
          {day && (
            <div id="day-panel" role="tabpanel" aria-labelledby={`tab-${sel}`}>
              <div className="day-sum">
                <span><b>Day</b><span>{dayLabel(day.date)}</span></span>
                <span><b>Stops</b><span>{(day.stops ?? []).length}</span></span>
                {travelMin > 0 && <span><b>Getting around</b><span>{duration(travelMin)}, {inr(travelCost)}</span></span>}
              </div>
              <div>
                {rows.map((r, i) =>
                  r.kind === "stop" ? (
                    <div className="it-row" key={i}>
                      <span className="it-time">{duration(r.place.typical_visit_minutes)}</span>
                      <span className="mk mk-stop">{r.n}</span>
                      <div className="it-body">
                        <b>{r.place.name}</b>
                        <small>{r.place.category[0].toUpperCase() + r.place.category.slice(1)} · about {duration(r.place.typical_visit_minutes)} there</small>
                      </div>
                      {planId && (
                        <button type="button" className="btn btn-quiet btn-sm it-swap" disabled={!!busy} aria-label={`Swap ${r.place.name} for something else`}
                          onClick={() => revise({ intent: "swap_stop", day: day.date, place_id: r.place.id }, `swapped ${r.place.name}`)}>
                          Swap
                        </button>
                      )}
                    </div>
                  ) : r.kind === "move" ? (
                    <div className="it-row" key={i}>
                      <span className="it-time">{clock(r.leg.depart)}</span>
                      <span className="mk mk-move"><svg className="ic" viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14" /><path d="M13 6l6 6-6 6" /></svg></span>
                      <div className="it-body">
                        <b>{MODE_NAME[r.leg.mode]} to {r.leg.to}</b>
                        <small>{duration(r.leg.minutes)} · {inr(r.leg.cost_inr)}</small>
                      </div>
                    </div>
                  ) : (
                    <div className="it-row" key={i}>
                      <span className="it-time">Night</span>
                      <span className="mk mk-stay"><svg className="ic" viewBox="0 0 24 24" aria-hidden="true"><path d="M3 18V7" /><path d="M3 14h18v4" /><path d="M3 11h7a2 2 0 0 1 2 2v1" /><path d="M12 14v-2a2 2 0 0 1 2-2h5a2 2 0 0 1 2 2v2" /></svg></span>
                      <div className="it-body"><b>{r.name}</b><small>Your base for the night</small></div>
                    </div>
                  ),
                )}
                {rows.length === 0 && <p className="hint">Nothing planned. A day to rest.</p>}
              </div>
              {(day.notes ?? []).length > 0 && (
                <div className="panel panel-pad" style={{ marginTop: 16 }}>
                  <h2 className="h3" style={{ marginBottom: 8 }}>Notes for the day</h2>
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
              caption={`${dayLabel(day.date)}: ${(day.stops ?? []).length} stop${(day.stops ?? []).length > 1 ? "s" : ""}, numbered in order`}
            />
          )}
          {planId && day && (
            <section className="panel" aria-labelledby="ch-h">
              <div className="panel-head"><h2 className="h3" id="ch-h">Change {weekday(day.date)}</h2><span className="hint">Only this day is rebuilt</span></div>
              <div className="panel-pad" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                <button type="button" className="btn btn-quiet" disabled={!!busy || !(day.stops ?? []).length}
                  onClick={() => revise({ intent: "lighter_day", day: day.date }, `${weekday(day.date)} is lighter`)}>
                  Make {weekday(day.date)} lighter
                </button>
                <button type="button" className="btn btn-quiet" disabled={!!busy}
                  onClick={() => revise({ intent: "rain", day: day.date }, `${weekday(day.date)} is planned for rain`)}>
                  Plan {weekday(day.date)} for rain
                </button>
                <p role="status" className={said?.bad ? "rev-msg bad" : "rev-msg"} hidden={!busy && !said}>
                  {busy ? "Rebuilding the day…" : said?.text}
                </p>
              </div>
            </section>
          )}
          <section className="panel panel-pad" aria-labelledby="b-h">
            <h2 className="h3" id="b-h" style={{ marginBottom: 14 }}>The budget</h2>
            <dl className="kv cost">
              <dt>Getting there{way ? `, ${MODE_NAME[way.mode].toLowerCase()}` : ""}</dt><dd>{inr(way ? way.total_cost_inr : it.budget.transport_inr)}</dd>
              <dt>Stay</dt><dd>{inr(it.budget.stay_inr)}</dd>
              {!!it.budget.food_inr && <><dt>Food</dt><dd>{inr(it.budget.food_inr)}</dd></>}
              {!!it.budget.activities_inr && <><dt>Tickets and activities</dt><dd>{inr(it.budget.activities_inr)}</dd></>}
              <dt className="tot">Whole trip, estimated</dt><dd className="tot">{inr(cost)}</dd>
            </dl>
          </section>
          {stay && (
            <section className="panel panel-pad" aria-labelledby="s-h">
              <h2 className="h3" id="s-h" style={{ marginBottom: 8 }}>Where you stay</h2>
              <p style={{ margin: 0 }}><b>{stay.name}</b>, {stay.city}</p>
              <p className="hint" style={{ margin: "4px 0 0" }}>{dayLabel(stay.check_in)} to {dayLabel(stay.check_out)} · {inr(stay.price_per_night_inr)} a night</p>
            </section>
          )}
          {(it.warnings ?? []).length > 0 && (
            <section aria-labelledby="w-h">
              <h2 className="h3" id="w-h" style={{ marginBottom: 8 }}>Good to know</h2>
              <ul className="warn-list">{it.warnings!.map((w) => <li key={w}>{w}</li>)}</ul>
            </section>
          )}
        </aside>
      </div>

      <div className="next">
        <div><b>Happy with it? Book it.</b><span>Trains, the stay and the cabs. We line them up; you pay the seller directly.</span></div>
        <div className="row-wrap">
          <Link className="btn btn-on-dark" href="/plan/options/">Change how you travel</Link>
          <Link className="btn btn-primary btn-lg" href="/book/">Book this plan</Link>
        </div>
      </div>
    </>
  );
}

export default function ItineraryPage() {
  const res = usePlanResult();
  return <AppShell>{res === undefined ? null : res ? <div><Plan it={res.itinerary} planId={res.plan_id} shareToken={res.share_token ?? null} /></div> : <NoPlan />}</AppShell>;
}
