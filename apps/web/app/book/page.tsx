"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { NoPlan } from "@/components/NoPlan";
import { Problem, problemOf } from "@/components/Problem";
import { Trail } from "@/components/Trail";
import { StayFacts, StayPick } from "@/components/StayFacts";
import type { BookedJourney, Itinerary, Mode, SellerOffer, TransportOption } from "@/lib/contracts";
import { MODE_ICON, MODE_NAME, clock, dayLabel, duration, inr } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { track } from "@/lib/metrics";
import { usePlanResult } from "@/lib/plan";
import { againstBudget, pickIndex, planTotal, railOptionLeg, stayGroups, trainDiffers, trainLeg } from "@/lib/planView";
import { SAMPLE_PNRS, cardCopyText, cardParty, cardRows, irctcCard, isDemoPlan, pnrStatus, type IrctcCard, type PnrStatus } from "@/lib/routes";
import { useRevise } from "@/lib/useRevise";
import "./book.css";

type Load<T> = { data?: T; problem?: { message: string; retryable: boolean } } | null;

// Whole phrases per mode, so each language can word them its own way.
const CHOOSE: Record<Mode, string> = { rail: "Choose rail", air: "Choose air", road: "Choose road" };

function Offers({ offers }: { offers?: SellerOffer[] }) {
  const { t } = useI18n();
  if (!offers?.length) return <small className="hint">{t("Seller prices and links come next.")}</small>;
  return (
    <ul className="offers">
      {offers.map((o) => (
        <li key={o.seller + o.url}>
          <span>{o.seller}</span>
          <span className="price">{o.price_inr != null ? inr(o.price_inr) : t("Check price")}</span>
          <a className="btn btn-quiet btn-sm" href={o.url} target="_blank" rel="noopener noreferrer" onClick={() => track("booking_chosen")}>
            {o.kind === "deep_link" ? t("Open") : t("Check")}
          </a>
        </li>
      ))}
    </ul>
  );
}

/** The main leg of an option (the train or flight itself, not the cab to the station). */
const mainLeg = (o: TransportOption) => o.legs.find((l) => l.mode === o.mode) ?? o.legs[0];
/** "2026-12-11T21:00:00" to the value of an <input type="datetime-local"> */
const toLocal = (iso: string) => iso.slice(0, 16);

/**
 * "I've booked this": the train or flight number and its times. TY1's booked intent re-times
 * the plan around the journey the traveller really has.
 */
function BookedForm({ o, busy, onSend, onCancel }: { o: TransportOption; busy: boolean; onSend: (b: BookedJourney) => void; onCancel: () => void }) {
  const { t } = useI18n();
  const leg = mainLeg(o);
  const [ref, setRef] = useState(leg?.ref ?? "");
  const [depart, setDepart] = useState(leg ? toLocal(leg.depart) : "");
  const [arrive, setArrive] = useState(leg ? toLocal(leg.arrive) : "");
  const [tried, setTried] = useState(false);
  const needsRef = o.mode !== "road";
  const problem = needsRef && !ref.trim() ? t(o.mode === "rail" ? "Enter the train number." : "Enter the flight number.") : !depart || !arrive ? t("Enter when it leaves and arrives.") : arrive <= depart ? t("It must arrive after it leaves.") : null;
  if (!leg) return null;
  return (
    <form
      className="booked"
      onSubmit={(e) => {
        e.preventDefault();
        setTried(true);
        if (problem) return;
        onSend({ mode: o.mode, ref: ref.trim(), from: leg.from, to: leg.to, depart: `${depart}:00`, arrive: `${arrive}:00` });
      }}
    >
      {needsRef && (
        <label className="field">
          <span className="label">{t(o.mode === "rail" ? "Train number" : "Flight number")}</span>
          <input className="input" value={ref} maxLength={12} autoComplete="off" placeholder={o.mode === "rail" ? "17309" : "6E 123"} onChange={(e) => setRef(e.target.value)} />
        </label>
      )}
      <label className="field">
        <span className="label">{t("Leaves")}</span>
        <input className="input" type="datetime-local" value={depart} onChange={(e) => setDepart(e.target.value)} />
      </label>
      <label className="field">
        <span className="label">{t("Arrives")}</span>
        <input className="input" type="datetime-local" value={arrive} min={depart} onChange={(e) => setArrive(e.target.value)} />
      </label>
      {tried && problem && <p className="rev-msg bad" role="alert">{problem}</p>}
      <div className="row-wrap">
        <button type="submit" className="btn btn-primary btn-sm" disabled={busy}>{t("Update my plan")}</button>
        <button type="button" className="btn btn-quiet btn-sm" onClick={onCancel}>{t("Cancel")}</button>
      </div>
    </form>
  );
}

// The plan's own options (TY1's Itinerary.transport), not a fresh compare: one source for Options,
// Book and the share link (QA #104). The one in use is the mode the days were built with.
function Travel({ it, planId }: { it: Itinerary; planId: string | null }) {
  const { lang, t } = useI18n();
  const { busy, said, revise } = useRevise(planId, it.lang);
  const travellers = it.request.constraints?.travellers?.length || 1;
  const opts = it.transport ?? [];
  const inUse = pickIndex(it);
  const [booking, setBooking] = useState<number | null>(null);
  const booked = async (b: BookedJourney) => {
    const what = b.ref ? `${t(MODE_NAME[b.mode]).toLowerCase()} ${b.ref}` : t(MODE_NAME[b.mode]).toLowerCase();
    if (await revise({ intent: "booked", booked: b }, t("Done: the plan now follows your {what}.", { what }))) setBooking(null);
  };

  return (
    <section className="bk-sec" aria-labelledby="go-h">
      <div className="bk-sec-head">
        <h2 className="h2" id="go-h">{t("Getting there")}</h2>
        <span className="hint">{t("{from} to {to}, {date}, for {n}", { from: it.request.origin, to: it.request.destinations.join(", "), date: dayLabel(it.request.start_date, lang), n: travellers })}</span>
      </div>
      <div className="opts3">
        {opts.map((o, i) => {
          const on = i === inUse;
          const changes = Math.max(0, o.legs.length - 1);
          return (
            <article key={`${o.mode}-${i}`} className={on ? "o3 on" : "o3"} aria-label={t(MODE_NAME[o.mode])}>
              <div className="o3-top">
                <svg className="ic" viewBox="0 0 24 24" aria-hidden="true"><path d={MODE_ICON[o.mode]} /></svg>
                <b>{t(MODE_NAME[o.mode])}</b>
                {on && <span className="badge badge-sea">{t("In your plan")}</span>}
                {o.legs.some((l) => l.booked) && <span className="badge badge-ok">{t("Booked")}</span>}
              </div>
              <span className="price">{inr(o.total_cost_inr)}</span>
              {o.mode === "road" && <small>{t("By car: fuel + tolls")}</small>}
              <small>{duration(o.total_minutes)} · {changes === 0 ? t("direct") : changes > 1 ? t("{n} changes", { n: changes }) : t("{n} change", { n: changes })} · {o.legs.map((l) => l.to).join(" → ")}</small>
              <Offers offers={o.offers} />
              {!on && planId && (
                <button type="button" className="btn btn-quiet btn-sm" disabled={!!busy}
                  onClick={() => revise({ intent: "transport", mode: o.mode }, t("Done: the plan now goes by {mode}.", { mode: t(MODE_NAME[o.mode]).toLowerCase() }))}>
                  {t(CHOOSE[o.mode])}
                </button>
              )}
              {planId && booking !== i && (
                <button type="button" className="btn btn-quiet btn-sm" disabled={!!busy} onClick={() => setBooking(i)}>{t("I've booked this")}</button>
              )}
              {planId && booking === i && <BookedForm o={o} busy={!!busy} onSend={(b) => void booked(b)} onCancel={() => setBooking(null)} />}
            </article>
          );
        })}
      </div>
      <p role="status" className={said?.bad ? "rev-msg bad" : "rev-msg"} hidden={!busy && !said}>
        {busy ? t("Rebuilding…") : said?.text}
      </p>
    </section>
  );
}

function TrainCard({ it, planId }: { it: Itinerary; planId: string | null }) {
  // The plan's own train, so the card names the same one as Options and the Itinerary (QA #101).
  // TY3: the rail option's own train leg (stations, number and time from that one leg), even when the
  // plan goes by road or air. No rail option: no card.
  const rail = useMemo(() => railOptionLeg(it), [it]);
  const [card, setCard] = useState<Load<IrctcCard>>(null);
  const [cls, setCls] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [run, setRun] = useState(0);
  const { t } = useI18n();

  useEffect(() => {
    if (!rail) return;
    const ctl = new AbortController();
    // TY3 picks the train by number when the leg has one (Leg.ref); else the first leaving at or after `after`.
    // No class unless the traveller picks one: TY3 uses the train's own default. Passenger rows follow the party size.
    const train = rail.ref && /^\d{5}$/.test(rail.ref) ? rail.ref : null;
    irctcCard({ from: rail.from, to: rail.to, date: rail.depart.slice(0, 10), ...cardParty(it, isDemoPlan(planId)), train, after: clock(rail.depart), travel_class: cls }, ctl.signal)
      .then((data) => setCard({ data }))
      .catch((e) => !ctl.signal.aborted && setCard({ problem: problemOf(e) }));
    return () => ctl.abort();
  }, [rail, it, run, cls, planId]);

  if (!rail) return null;
  const c = card?.data;
  // Real plans: the party's ages, names left for the traveller (never the sample family's).
  const demo = isDemoPlan(planId);
  const rows = c ? cardRows(c, it, demo) : [];
  const copy = async () => {
    if (!c) return;
    try {
      await navigator.clipboard.writeText(cardCopyText(c, rows, demo));
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };

  return (
    <section className="bk-sec" aria-labelledby="train-h">
      <div className="bk-sec-head">
        <h2 className="h2" id="train-h">{t("Train on IRCTC")}</h2>
        <span className="hint">{t("IRCTC has no booking link we can fill; copy these and paste them into its form.")}</span>
      </div>
      {!card ? (
        <p className="hint" role="status">{t("Getting the train details…")}</p>
      ) : card.problem ? (
        <Problem {...card.problem} onRetry={() => { setCard(null); setRun((r) => r + 1); }} />
      ) : (
        c && (
          <div className="copy">
            <div className="copy-head">
              <b>{t("Ready for IRCTC: {train}", { train: `${c.train.number} ${c.train.name}` })}</b>
              {c.sample && demo && <span className="badge">{t("Sample")}</span>}
            </div>
            <div className="cgrid">
              <div className="cfield"><small>{t("From")}</small><span>{c.from.code} · {c.from.name}</span></div>
              <div className="cfield"><small>{t("To")}</small><span>{c.to.code} · {c.to.name}</span></div>
              <div className="cfield"><small>{t("Date")}</small><span>{c.date_irctc}</span></div>
              <div className="cfield"><small>{t("Departs")}</small><span>{c.departs}</span></div>
              <div className="cfield"><small>{t("Arrives")}</small><span>{c.arrives}{c.arrives_day_offset ? ` (+${c.arrives_day_offset})` : ""}</span></div>
              <div className="cfield"><small>{t("Class · Quota")}</small><span>{c.travel_class} · {c.quota}</span></div>
            </div>
            {(c.classes?.length ?? 0) > 1 && (
              <div className="toggle wrap-toggle" role="group" aria-label={t("Class")}>
                {c.classes!.map((k) => (
                  <button key={k} type="button" className={k === c.travel_class ? "on" : undefined} aria-pressed={k === c.travel_class} onClick={() => { setCard(null); setCls(k); }}>{k}</button>
                ))}
              </div>
            )}
            <div className="table-scroll">
              <table className="ptable">
                <thead><tr><th>{t("Passenger")}</th><th>{t("Age")}</th><th>{t("Gender")}</th><th>{t("Berth")}</th></tr></thead>
                <tbody>{rows.map((p, i) => <tr key={i}><td>{p.name || <span className="hint">{t("Passenger {n}: name as on ID", { n: i + 1 })}</span>}</td><td>{p.age ?? "—"}</td><td>{p.gender || "—"}</td><td>{t(p.berth)}</td></tr>)}</tbody>
              </table>
            </div>
            {trainDiffers(rail, c, it) && (
              <p className="badge badge-warn">{t("Your plan's train leaves at {time}; this one leaves at {other}. Pick the plan's train on IRCTC.", { time: clock(trainLeg(it)?.depart ?? rail.depart), other: c.departs })}</p>
            )}
            <p>{t("About {fare} for everyone.", { fare: inr(c.fare_estimate_inr) })} {c.notes.join(" ")}</p>
            <div className="row-wrap">
              <button type="button" className="btn btn-cream" onClick={copy}>{copied ? t("Copied") : t("Copy all details")}</button>
              <a className="btn btn-primary" href={c.booking_url} target="_blank" rel="noopener noreferrer" onClick={() => track("booking_chosen")}>{t("Open IRCTC")}</a>
            </div>
          </div>
        )
      )}
    </section>
  );
}

function PnrTrack() {
  const [pnr, setPnr] = useState("");
  const [res, setRes] = useState<Load<PnrStatus> | "busy">(null);
  const { lang, t } = useI18n();
  const check = async (value: string) => {
    const v = value.replace(/\D/g, "");
    setPnr(v);
    if (v.length !== 10) return setRes({ problem: { message: "A PNR has 10 digits.", retryable: false } });
    setRes("busy");
    try {
      setRes({ data: await pnrStatus(v) });
    } catch (e) {
      setRes({ problem: problemOf(e) });
    }
  };
  const s = res && res !== "busy" ? res.data : undefined;
  return (
    <section className="bk-sec" aria-labelledby="pnr-h">
      <div className="bk-sec-head"><h2 className="h2" id="pnr-h">{t("Track a PNR")}</h2><span className="hint">{t("Sample PNRs only in the prototype.")}</span></div>
      <form className="track" onSubmit={(e) => { e.preventDefault(); void check(pnr); }}>
        <label htmlFor="pnr" className="sr">{t("PNR number")}</label>
        <input id="pnr" className="input" inputMode="numeric" maxLength={10} placeholder={t("10-digit PNR")} value={pnr} onChange={(e) => setPnr(e.target.value)} />
        <button type="submit" className="btn btn-primary" disabled={res === "busy"}>{t("Check")}</button>
      </form>
      <div className="q-chips">{SAMPLE_PNRS.map((p) => <button key={p} type="button" className="chip" onClick={() => void check(p)}>{p}</button>)}</div>
      {res === "busy" ? (
        <p className="hint" role="status">{t("Checking…")}</p>
      ) : res?.problem ? (
        <Problem {...res.problem} onRetry={() => void check(pnr)} />
      ) : s && (
        <div className="panel panel-pad pnr">
          <div className="bk-sec-head">
            <b>{s.train} · {s.class} · {dayLabel(s.date, lang)}</b>
            <span className={/CNF/.test(s.current_status) ? "badge badge-ok" : "badge badge-warn"}>{s.current_status}</span>
          </div>
          <p className="hint" style={{ margin: 0 }}>{s.chart_prepared ? t("{from} to {to} · chart prepared", { from: s.from.name, to: s.to.name }) : t("{from} to {to}", { from: s.from.name, to: s.to.name })}</p>
          <ol className="timeline">
            {[...s.timeline].sort((a, b) => Date.parse(b.at) - Date.parse(a.at)).map((e) => (
              <li key={e.at + e.status}><time dateTime={e.at}>{dayLabel(e.at, lang)} {e.at.slice(11, 16)}</time><i /><span><b>{e.status}</b> {e.note}</span></li>
            ))}
          </ol>
        </div>
      )}
    </section>
  );
}

function Book({ it, planId }: { it: Itinerary; planId: string | null }) {
  // The one budget: TY1's total, the same number on every page.
  const cost = planTotal(it);
  const vs = againstBudget(it, cost);
  const { lang, t } = useI18n();
  const { busy, said, revise } = useRevise(planId, it.lang);
  return (
    <>
      <div className="bk-top">
        <Trail at={5} />
        <h1 className="page-title">{t("Book {places}", { places: it.request.destinations.join(` ${t("and")} `) })}</h1>
        <p className="page-sub">{t("We line everything up; you book and pay each seller directly. Nothing here charges you.")}</p>
      </div>
      <div className="bk-strip">
        <div><small>{t("Whole trip, estimated")}</small><b>{inr(cost)}</b></div>
        <div><small>{t("Budget")}</small><b>{it.request.constraints?.budget_inr ? inr(it.request.constraints.budget_inr) : t("Not set")}</b></div>
        <div><small>{vs && !vs.ok ? t("Over budget by") : t("Left over")}</small><b>{vs ? inr(vs.diff) : "—"}</b></div>
      </div>
      <Travel it={it} planId={planId} />
      <TrainCard it={it} planId={planId} />
      <section className="bk-sec" aria-labelledby="stay-h">
        <div className="bk-sec-head"><h2 className="h2" id="stay-h">{t("Where you stay")}</h2></div>
        {stayGroups(it).map(({ chosen: s, others }) => (
          <article key={s.id ?? s.name + s.check_in} className="item">
            <span className="item-ic"><svg className="ic" viewBox="0 0 24 24" aria-hidden="true"><path d="M3 18V7" /><path d="M3 14h18v4" /><path d="M3 11h7a2 2 0 0 1 2 2v1" /><path d="M12 14v-2a2 2 0 0 1 2-2h5a2 2 0 0 1 2 2v2" /></svg></span>
            <div>
              <b>{s.name}</b>
              <span className="item-sub">{t("{city} · {from} to {to} · {price} a night", { city: s.city, from: dayLabel(s.check_in, lang), to: dayLabel(s.check_out, lang), price: inr(s.price_per_night_inr) })}</span>
              <StayFacts stay={s} />
              <Offers offers={s.offers} />
              {planId && others.length > 0 && (
                <details className="stay-others">
                  <summary>{t("Other stays in {city} ({n})", { city: s.city, n: others.length })}</summary>
                  <ul>
                    {others.map((o) => (
                      <li key={o.id ?? o.name}>
                        <div>
                          <b>{o.name}</b>
                          <span className="item-sub">{t("{price} a night", { price: inr(o.price_per_night_inr) })}</span>
                          <StayFacts stay={o} />
                        </div>
                        {o.id && (
                          <button type="button" className="btn btn-quiet btn-sm" disabled={!!busy}
                            onClick={() => void revise({ intent: "change_stay", stay_id: o.id }, t("Done: you stay at {name}.", { name: o.name }))}>
                            {t("Choose this stay")}
                          </button>
                        )}
                      </li>
                    ))}
                  </ul>
                </details>
              )}
              {planId && !others.length && <StayPick stay={s} busy={!!busy} revise={revise} />}
            </div>
          </article>
        ))}
        {!(it.stays ?? []).length && <p className="hint">{t("No stay in this plan.")}</p>}
        <p role="status" className={said?.bad ? "rev-msg bad" : "rev-msg"} hidden={!busy && !said}>{busy ? t("Rebuilding…") : said?.text}</p>
      </section>
      <section className="bk-sec" aria-labelledby="cab-h">
        <div className="bk-sec-head"><h2 className="h2" id="cab-h">{t("Cabs")}</h2></div>
        <p className="hint" style={{ margin: 0 }}>{t("Local cabs are booked on the day. Seller links for cabs come with the seller comparison.")}</p>
      </section>
      <PnrTrack />
      <div className="go">
        <div>
          <b>{t("Next: Katha")}</b>
          <span>{t("The story of each day's stops, to hear on the way.")}</span>
        </div>
        <Link className="btn btn-primary btn-lg" href="/katha/day/">{t("Next: Katha")}</Link>
      </div>
      <p><Link href="/plan/itinerary/">{t("Back to the day-by-day plan")}</Link></p>
    </>
  );
}

export default function BookPage() {
  const res = usePlanResult();
  return <AppShell>{res === undefined ? null : res ? <div><Book it={res.itinerary} planId={res.plan_id} /></div> : <NoPlan />}</AppShell>;
}
