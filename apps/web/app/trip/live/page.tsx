"use client";

// Trip mode (design/prototype/TripLive.dc.html): pick a saved trip, share your
// location, and see where you are against today's plan. "Running late" asks
// TY1's planner to re-plan the rest of the day; the nearest hospital and
// what is near you come from TY2's guide (Google Places, never written by a model).

import Link from "next/link";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { Problem, problemOf } from "@/components/Problem";
import { listTrips, useAccount, type SavedTrip } from "@/lib/account";
import { API_BASE_URL } from "@/lib/api";
import type { Itinerary, Lang, PlanEvent } from "@/lib/contracts";
import { dayLabel } from "@/lib/format";
import { askGuide } from "@/lib/guide";
import { ApiError, apiJSON, query } from "@/lib/http";
import { useI18n } from "@/lib/i18n";
import { GOA_ITINERARY, SAMPLE_SHARE_TOKEN } from "@/lib/mockPlan";
import { streamRevise } from "@/lib/plan";
import {
  addMinutes, clockText, distanceText, localNow, mapsLink, metres, nearbyFrom, slots, status, todayIndex, type Where,
} from "./live";
import "./live.css";

type Loaded = { itinerary: Itinerary; plan_id: string | null; title: string; sample: boolean };
type NearPlace = { name: string; metres: number; lat: number; lng: number; maps_url?: string };
type Near = { kind: Kind; places: NearPlace[] } | { kind: Kind; problem: string };
type NearbyOut = { name: string; kind: string; lat: number; lng: number; distance_m: number; maps_url: string };
type Kind = "hospital" | "pharmacy" | "food";

const SAMPLE: SavedTrip = {
  plan_id: "sample-goa-family",
  share_token: SAMPLE_SHARE_TOKEN,
  title: "Bengaluru to Goa (sample trip)",
  origin: GOA_ITINERARY.request.origin,
  destinations: GOA_ITINERARY.request.destinations,
  start_date: GOA_ITINERARY.request.start_date,
  end_date: GOA_ITINERARY.request.end_date,
  created_at: "2026-10-01T00:00:00Z",
  itinerary: GOA_ITINERARY,
};

const LATE = [15, 30, 60];
const QUESTION: Record<Exclude<Kind, "food">, string> = { hospital: "Where is the nearest hospital?", pharmacy: "Where is the nearest pharmacy?" };

/**
 * GET /guide/nearby (TY2): cached Google Places, nearest first (hospitals: larger
 * ones first). With no API, or before that route is deployed, hospital and
 * pharmacy fall back to the guide's emergency answer and food to the sample.
 */
async function nearby(kind: "food" | "veg" | "pharmacy" | "hospital", where: Where, city: string | undefined, lang: Lang): Promise<NearPlace[]> {
  if (API_BASE_URL) {
    try {
      const r = await apiJSON<NearbyOut[]>(`/guide/nearby${query({ lat: where.lat, lng: where.lng, kind, limit: 3 })}`);
      return r.map((p) => ({ name: p.name, metres: p.distance_m, lat: p.lat, lng: p.lng, maps_url: p.maps_url }));
    } catch (e) {
      if (!(e instanceof ApiError && (e.status === 404 || e.status === 405)) || kind === "food" || kind === "veg") throw e;
    }
  }
  if (kind === "food" || kind === "veg") return [];
  const a = await askGuide({ question: QUESTION[kind], lat: where.lat, lng: where.lng, city, lang });
  const all = nearbyFrom(a, where);
  // The answer can list police too; keep the kind asked for when the places say what they are.
  const same = all.filter((x) => x.place.category.toLowerCase().includes(kind));
  return (same.length ? same : all).slice(0, 3).map(({ place, metres: m }) => ({ name: place.name, metres: m, lat: place.lat, lng: place.lng }));
}

function useClock(): string {
  const [now, setNow] = useState(() => localNow());
  useEffect(() => {
    const id = setInterval(() => setNow(localNow()), 30_000);
    return () => clearInterval(id);
  }, []);
  return now;
}

export default function TripLivePage() {
  return (
    <Suspense>
      <TripLive />
    </Suspense>
  );
}

function TripLive() {
  const { lang, t } = useI18n();
  const account = useAccount();
  const params = useSearchParams();
  const clock = useClock();
  const [trips, setTrips] = useState<SavedTrip[] | null>(null);
  const [listProblem, setListProblem] = useState<{ message: string; retryable: boolean } | null>(null);
  const [pick, setPick] = useState<string | null>(params.get("trip"));
  const [trip, setTrip] = useState<Loaded | null>(null);
  const [loadProblem, setLoadProblem] = useState<{ message: string; retryable: boolean } | null>(null);
  const [previewDay, setPreviewDay] = useState<number | null>(null);
  const [previewTime, setPreviewTime] = useState("10:00");
  const [where, setWhere] = useState<Where | null>(null);
  const [geoNote, setGeoNote] = useState<string | null>(null);
  const watch = useRef<number | null>(null);
  const [replan, setReplan] = useState<{ busy: boolean; note?: string; bad?: boolean }>({ busy: false });
  const [near, setNear] = useState<Near | null>(null);
  const [nearBusy, setNearBusy] = useState<Kind | null>(null);

  // Saved trips: the API's or this browser's; with no API, the sample trip too.
  useEffect(() => {
    let live = true;
    listTrips()
      .then((r) => live && setTrips(API_BASE_URL ? r.trips : [...r.trips, SAMPLE]))
      .catch((e) => live && setListProblem(problemOf(e)));
    return () => {
      live = false;
    };
  }, []);

  // Open the picked trip: in full from this browser, else its share page's plan.
  useEffect(() => {
    if (!pick || !trips) return;
    const s = trips.find((x) => x.plan_id === pick);
    if (!s) return;
    let live = true;
    (s.itinerary ? Promise.resolve(s.itinerary) : apiJSON<Itinerary>(`/trips/${encodeURIComponent(s.share_token)}`))
      .then((itinerary) => live && setTrip({ itinerary, plan_id: s.plan_id, title: s.title, sample: s === SAMPLE }))
      .catch((e) => live && setLoadProblem(problemOf(e)));
    return () => {
      live = false;
    };
  }, [pick, trips]);

  useEffect(() => () => {
    if (watch.current !== null) navigator.geolocation.clearWatch(watch.current);
  }, []);

  const share = useCallback(() => {
    if (!("geolocation" in navigator)) {
      setGeoNote("This browser can't share its location.");
      return;
    }
    setGeoNote("Finding you…");
    watch.current = navigator.geolocation.watchPosition(
      (p) => {
        setWhere({ lat: p.coords.latitude, lng: p.coords.longitude, accuracy: Math.min(p.coords.accuracy, 500) });
        setGeoNote(null);
      },
      (e) => setGeoNote(e.code === e.PERMISSION_DENIED ? "Location is blocked for this site. Allow it in the browser to use trip mode." : "Couldn't find your location just now."),
      { enableHighAccuracy: true, maximumAge: 30_000, timeout: 20_000 },
    );
  }, []);

  const choose = (planId: string | null) => {
    setPick(planId);
    setTrip(null);
    setLoadProblem(null);
    setPreviewDay(null);
    setReplan({ busy: false });
    setNear(null);
  };

  const stopSharing = () => {
    if (watch.current !== null) navigator.geolocation.clearWatch(watch.current);
    watch.current = null;
    setWhere(null);
    setNear(null);
  };

  const it = trip?.itinerary;
  const today = it ? todayIndex(it, clock) : -1;
  const dayIdx = today >= 0 ? today : previewDay;
  const preview = today < 0 && previewDay !== null;
  const now = it && dayIdx !== null && dayIdx >= 0 ? (preview ? `${it.days[dayIdx].date}T${previewTime}` : clock) : clock;
  const day = it && dayIdx !== null && dayIdx >= 0 ? it.days[dayIdx] : null;
  const st = useMemo(() => (day ? status(day, now, where) : null), [day, now, where]);
  const list = useMemo(() => (day ? slots(day) : []), [day]);

  async function runLate(minutes: number) {
    if (!trip?.plan_id) return;
    setReplan({ busy: true, note: "Re-planning the rest of today…" });
    const body = { intent: "rest_of_day" as const, now: `${addMinutes(now, minutes)}:00`, lat: where?.lat ?? null, lng: where?.lng ?? null, lang };
    try {
      let changed: string | undefined;
      let last: PlanEvent | undefined;
      if (trip.sample) {
        // No API: the sample day drops its last stop, as the planner would to end on time.
        const d = trip.itinerary.days[dayIdx!];
        const drop = d.stops?.at(-1);
        const days = trip.itinerary.days.map((x, i) => (i === dayIdx && drop ? { ...x, stops: x.stops?.filter((s) => s !== drop), legs: x.legs?.filter((l) => l.to !== drop.name && l.from !== drop.name), schedule: x.schedule?.filter((s) => s.place_id !== drop.id) } : x));
        changed = drop ? `Dropped ${drop.name} so the day still ends on time (sample).` : "Nothing to move.";
        last = { stage: "done", message: "", partial: { ...trip.itinerary, days }, plan_id: trip.plan_id };
      } else {
        for await (const ev of streamRevise(trip.plan_id, body)) {
          if (ev.stage === "solving" && !changed) changed = ev.message;
          last = ev;
        }
      }
      if (last?.stage === "done" && last.partial) {
        setTrip({ ...trip, itinerary: last.partial, plan_id: last.plan_id ?? trip.plan_id });
        setReplan({ busy: false, note: changed || "The rest of today is re-planned." });
      } else {
        setReplan({ busy: false, bad: true, note: last?.message || "The planner couldn't re-plan today." });
      }
    } catch (e) {
      setReplan({ busy: false, bad: true, note: problemOf(e).message });
    }
  }

  async function findNear(kind: Kind) {
    if (!where || !it) return;
    setNearBusy(kind);
    setNear(null);
    const veg = it.request.constraints?.dietary?.some((d) => /veg/i.test(d));
    try {
      setNear({ kind, places: await nearby(kind === "food" && veg ? "veg" : kind, where, it.request.destinations[0], lang) });
    } catch (e) {
      setNear({ kind, problem: problemOf(e).message });
    } finally {
      setNearBusy(null);
    }
  }

  return (
    <AppShell>
      <div className="wrap live-page">
        {!trip && (
          <section className="panel panel-pad" aria-labelledby="pick-h">
            <p className="eyebrow">{t("Trip mode")}</p>
            <h1 className="page-title" id="pick-h">{t("Which trip are you on?")}</h1>
            <p className="hint">{t("Pick a saved trip. On the days of the trip this page shows where you are against the plan.")}</p>
            {listProblem && <Problem {...listProblem} />}
            {loadProblem && <Problem {...loadProblem} />}
            {trips === null && !listProblem && <p className="hint" role="status">{t("Loading your trips…")}</p>}
            {trips && trips.length === 0 && (
              <p>{t("No saved trips yet.")} <Link href="/plan/start/">{t("Plan a trip")}</Link></p>
            )}
            <ul className="live-trips">
              {trips?.map((s) => (
                <li key={s.plan_id}>
                  <button type="button" className="live-trip" onClick={() => choose(s.plan_id)} disabled={pick === s.plan_id && !loadProblem}>
                    <b>{s.title}</b>
                    <span>{dayLabel(s.start_date, lang)} – {dayLabel(s.end_date, lang)}</span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}

        {trip && it && (
          <>
            <div className="tl-top">
              <div>
                <p className="eyebrow">
                  {trip.title}
                  {day && ` · ${t("Day {n} of {m}", { n: dayIdx! + 1, m: it.days.length })}`}
                </p>
                <h1 className="page-title">{day ? dayLabel(day.date, lang) : t("Not travelling today")}</h1>
              </div>
              <div className="row-wrap">
                {trip.sample && <span className="badge badge-warn">{t("Sample trip")}</span>}
                {preview && <span className="badge badge-warn">{t("Preview at {time}", { time: clockText(now) })}</span>}
                <button type="button" className="btn btn-quiet btn-sm" onClick={() => choose(null)}>{t("Other trip")}</button>
                <Link className="btn btn-quiet btn-sm" href="/ask/">{t("Ask the guide")}</Link>
              </div>
            </div>

            {today < 0 && (
              <section className="panel panel-pad live-off">
                <p>{t("This trip runs from {a} to {b}. On those days this page follows you through the plan.", { a: dayLabel(it.request.start_date, lang), b: dayLabel(it.request.end_date, lang) })}</p>
                <div className="row-wrap">
                  <label className="hint" htmlFor="pv-day">{t("Preview a day")}</label>
                  <select id="pv-day" value={previewDay ?? ""} onChange={(e) => setPreviewDay(e.target.value === "" ? null : Number(e.target.value))}>
                    <option value="">{t("Choose")}</option>
                    {it.days.map((d, i) => <option key={d.date} value={i}>{dayLabel(d.date, lang)}</option>)}
                  </select>
                  {previewDay !== null && (
                    <input type="time" aria-label={t("Preview time")} value={previewTime} step={900} onChange={(e) => setPreviewTime(e.target.value || "10:00")} />
                  )}
                </div>
              </section>
            )}

            {day && st && (
              <div className="split">
                <div className="main" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                  <section className="now" aria-labelledby="now-h">
                    <div className="now-body">
                      <span className="now-k">
                        {where && <span className="live" aria-hidden="true" />}
                        {st.current
                          ? st.here ? t("You are here · {time}", { time: clockText(now) }) : t("On the plan now · {time}", { time: clockText(now) })
                          : st.done ? t("Today's plan is done") : t("Now · {time}", { time: clockText(now) })}
                      </span>
                      <h2 id="now-h">{st.current ? st.current.place.name : st.next ? t("On the way") : t("Back at your stay")}</h2>
                      {st.current && (
                        <p>{t(st.current.planned ? "Until {time}." : "Until about {time}.", { time: clockText(st.current.leave) })}</p>
                      )}
                      {st.next ? (
                        <div className="next-up">
                          <div>
                            <b>{t("Next: {name} at {time}", { name: st.next.place.name, time: clockText(st.next.arrive) })}</b>
                            <span>
                              {st.distance !== null && st.eta
                                ? t(st.eta.by === "walk" ? "{d} away, about {m} min on foot." : "{d} away, about {m} min by road.", { d: distanceText(st.distance), m: st.eta.minutes })
                                : t("Share your location to see how far it is.")}
                              {st.late ? ` ${t("You may be about {m} min late.", { m: st.late })}` : st.distance !== null ? ` ${t("You're on time.")}` : ""}
                            </span>
                          </div>
                          <a className="btn btn-sm live-go" href={mapsLink(st.next.place)} target="_blank" rel="noreferrer">{t("Directions")}</a>
                        </div>
                      ) : null}
                    </div>
                  </section>

                  <section className="panel panel-pad" aria-labelledby="loc-h">
                    <h2 className="h3" id="loc-h">{t("Your location")}</h2>
                    {where ? (
                      <p className="hint">
                        {t("Shared, to within about {m} m.", { m: Math.round(where.accuracy ?? 50) })}{" "}
                        <button type="button" className="linkish" onClick={stopSharing}>{t("Stop sharing")}</button>
                      </p>
                    ) : account?.consents.location ? (
                      <button type="button" className="btn btn-primary btn-sm" onClick={share}>{t("Share my location")}</button>
                    ) : (
                      <p className="hint">{t("Trip mode needs your location.")} <Link href="/settings/">{t("Turn on location in Settings")}</Link></p>
                    )}
                    {geoNote && <p className="hint" role="status">{t(geoNote)}</p>}
                    <p className="hint">{t("Your location stays on this phone. It is sent only when you ask for what's near you or re-plan the day, and is not stored.")}</p>
                  </section>

                  <section className="panel panel-pad" aria-labelledby="late-h">
                    <h2 className="h3" id="late-h">{t("Running late?")}</h2>
                    <p className="hint">{t("Tell us by how much and the rest of today is re-planned: stops that no longer fit are moved or dropped, and the day still ends on time.")}</p>
                    {preview && !trip.sample ? (
                      <p className="hint">{t("Re-planning works on the day itself, not in a preview.")}</p>
                    ) : (
                      <div className="row-wrap">
                        {LATE.map((m) => (
                          <button key={m} type="button" className="btn btn-quiet btn-sm" disabled={replan.busy || !trip.plan_id || st.done} onClick={() => runLate(m)}>
                            {m < 60 ? t("{m} min late", { m }) : t("An hour late")}
                          </button>
                        ))}
                      </div>
                    )}
                    {replan.note && <p className={replan.bad ? "hint bad" : "hint"} role="status">{t(replan.note)}</p>}
                  </section>
                </div>

                <aside className="side" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                  <section className="panel" aria-labelledby="today-h">
                    <div className="panel-head"><h2 className="h3" id="today-h">{t("Today")}</h2></div>
                    <ol className="panel-pad today">
                      {list.map((s, i) => {
                        const isNow = st.current?.place.id === s.place.id;
                        const past = !isNow && s.leave <= now;
                        return (
                          <li key={s.place.id} className={past ? "it-row past" : "it-row"}>
                            <time>{(s.planned ? "" : "~") + clockText(s.arrive)}</time>
                            <span className={isNow ? "dot now" : past ? "dot done" : "dot"}>{i + 1}</span>
                            <div>
                              <b>{s.place.name}</b>
                              <small>
                                {isNow ? t("Now") : past ? t("Done") : where ? distanceText(metres(where, s.place)) : t("Until {time}", { time: clockText(s.leave) })}
                              </small>
                            </div>
                          </li>
                        );
                      })}
                      {list.length === 0 && <li className="hint">{t("No stops planned for this day.")}</li>}
                    </ol>
                  </section>

                  <section className="panel panel-pad help" aria-labelledby="near-h">
                    <h2 className="h3" id="near-h">{t("Near you")}</h2>
                    <div className="row-wrap">
                      {(["food", "pharmacy", "hospital"] as Kind[]).map((k) => (
                        <button key={k} type="button" className="btn btn-quiet btn-sm" disabled={!where || nearBusy !== null} onClick={() => findNear(k)}>
                          {t(k === "food" ? "Food" : k === "pharmacy" ? "Pharmacy" : "Hospital")}
                        </button>
                      ))}
                    </div>
                    {!where && <p className="hint">{t("Share your location to find these.")}</p>}
                    {nearBusy && <p className="hint" role="status">{t("Looking…")}</p>}
                    {near && "problem" in near && <p className="hint bad" role="status">{t(near.problem)}</p>}
                    {near && !("problem" in near) && (
                      <ul className="near">
                        {near.places.map((p) => (
                          <li key={p.name + p.lat}>
                            <a href={p.maps_url || mapsLink(p)} target="_blank" rel="noreferrer"><b>{p.name}</b><span>{distanceText(p.metres)}</span></a>
                          </li>
                        ))}
                        {near.places.length === 0 && <li className="hint">{t(trip.sample ? "No sample places for this; the live app searches Google Maps." : "Nothing found close by.")}</li>}
                      </ul>
                    )}
                    <a className="btn btn-primary btn-block" href="tel:112">{t("Emergency: call 112")}</a>
                    <a className="btn btn-quiet btn-block" href="tel:108">{t("Ambulance: call 108")}</a>
                  </section>
                </aside>
              </div>
            )}
          </>
        )}
      </div>
    </AppShell>
  );
}
