"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { NoPlan } from "@/components/NoPlan";
import { Problem, problemOf } from "@/components/Problem";
import { Trail } from "@/components/Trail";
import type { CompareResponse, Itinerary, SellerOffer } from "@/lib/contracts";
import { MODE_ICON, MODE_NAME, dayLabel, duration, inr } from "@/lib/format";
import { track } from "@/lib/metrics";
import { saveChoice, useChoice, usePlanResult } from "@/lib/plan";
import { againstBudget, pickIndex, tripCost } from "@/lib/planView";
import { SAMPLE_PNRS, compareRoutes, irctcCard, partyFor, pnrStatus, type IrctcCard, type PnrStatus } from "@/lib/routes";
import "./book.css";

type Load<T> = { data?: T; problem?: { message: string; retryable: boolean } } | null;

function Offers({ offers }: { offers?: SellerOffer[] }) {
  if (!offers?.length) return <small className="hint">Seller prices and links come next.</small>;
  return (
    <ul className="offers">
      {offers.map((o) => (
        <li key={o.seller + o.url}>
          <span>{o.seller}</span>
          <span className="price">{o.price_inr != null ? inr(o.price_inr) : "Check price"}</span>
          <a className="btn btn-quiet btn-sm" href={o.url} target="_blank" rel="noopener noreferrer" onClick={() => track("booking_chosen")}>
            {o.kind === "deep_link" ? "Open" : "Check"}
          </a>
        </li>
      ))}
    </ul>
  );
}

function Travel({ it }: { it: Itinerary }) {
  const [cmp, setCmp] = useState<Load<CompareResponse>>(null);
  const [run, setRun] = useState(0);
  const stored = useChoice();
  const travellers = it.request.constraints?.travellers?.length || 1;

  useEffect(() => {
    const ctl = new AbortController();
    compareRoutes(
      { origin: it.request.origin, destination: it.request.destinations[0] ?? "", date: it.request.start_date, travellers },
      it,
      ctl.signal,
    )
      .then((data) => setCmp({ data }))
      .catch((e) => !ctl.signal.aborted && setCmp({ problem: problemOf(e) }));
    return () => ctl.abort();
  }, [it, travellers, run]);

  // Keep the mode chosen on PlanOptions highlighted here.
  const chosenMode = (it.transport ?? [])[stored ?? pickIndex(it)]?.mode;

  return (
    <section className="bk-sec" aria-labelledby="go-h">
      <div className="bk-sec-head">
        <h2 className="h2" id="go-h">Getting there</h2>
        <span className="hint">{it.request.origin} to {it.request.destinations.join(", ")}, {dayLabel(it.request.start_date)}, for {travellers}</span>
      </div>
      {!cmp ? (
        <p className="hint" role="status">Comparing road, rail and air…</p>
      ) : cmp.problem ? (
        <Problem {...cmp.problem} onRetry={() => { setCmp(null); setRun((r) => r + 1); }} />
      ) : (
        <>
          <div className="opts3">
            {cmp.data!.options.map((r) => {
              const o = r.option;
              const on = o.mode === chosenMode;
              return (
                <article key={r.id} className={on ? "o3 on" : "o3"} aria-label={`${MODE_NAME[o.mode]} option ${r.rank}`}>
                  <div className="o3-top">
                    <svg className="ic" viewBox="0 0 24 24" aria-hidden="true"><path d={MODE_ICON[o.mode]} /></svg>
                    <b>{MODE_NAME[o.mode]}</b>
                    {r.rank === 1 && <span className="badge badge-sea">Best match</span>}
                  </div>
                  <span className="price">{inr(o.total_cost_inr)}</span>
                  <small>{duration(o.total_minutes)} · {r.changes === 0 ? "direct" : `${r.changes} change${r.changes > 1 ? "s" : ""}`} · {o.legs.map((l) => l.to).join(" → ")}</small>
                  <Offers offers={o.offers} />
                  {!on && (
                    <button type="button" className="btn btn-quiet btn-sm" onClick={() => {
                      const i = (it.transport ?? []).findIndex((x) => x.mode === o.mode);
                      if (i >= 0) saveChoice(i);
                      track("booking_chosen");
                    }}>Choose {MODE_NAME[o.mode].toLowerCase()}</button>
                  )}
                </article>
              );
            })}
          </div>
          {(cmp.data!.unavailable ?? []).map((u) => (
            <p key={u.mode} className="unavail"><b>No {MODE_NAME[u.mode].toLowerCase()}:</b> {u.reason}</p>
          ))}
          {(cmp.data!.notes ?? []).map((n) => <p key={n} className="hint" style={{ margin: 0 }}>{n}</p>)}
        </>
      )}
    </section>
  );
}

function TrainCard({ it }: { it: Itinerary }) {
  const rail = (it.transport ?? []).flatMap((o) => o.legs).find((l) => l.mode === "rail");
  const [card, setCard] = useState<Load<IrctcCard>>(null);
  const [copied, setCopied] = useState(false);
  const [run, setRun] = useState(0);

  useEffect(() => {
    if (!rail) return;
    const ctl = new AbortController();
    irctcCard({ from: rail.from, to: rail.to, date: rail.depart.slice(0, 10), party: partyFor(it) }, ctl.signal)
      .then((data) => setCard({ data }))
      .catch((e) => !ctl.signal.aborted && setCard({ problem: problemOf(e) }));
    return () => ctl.abort();
  }, [rail, it, run]);

  if (!rail) return null;
  const c = card?.data;
  const copy = async () => {
    if (!c) return;
    try {
      await navigator.clipboard.writeText(c.copy_text);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };

  return (
    <section className="bk-sec" aria-labelledby="train-h">
      <div className="bk-sec-head">
        <h2 className="h2" id="train-h">Train on IRCTC</h2>
        <span className="hint">IRCTC has no booking link we can fill; copy these and paste them into its form.</span>
      </div>
      {!card ? (
        <p className="hint" role="status">Getting the train details…</p>
      ) : card.problem ? (
        <Problem {...card.problem} onRetry={() => { setCard(null); setRun((r) => r + 1); }} />
      ) : (
        c && (
          <div className="copy">
            <div className="copy-head">
              <b>Ready for IRCTC: {c.train.number} {c.train.name}</b>
              {c.sample && <span className="badge">Sample</span>}
            </div>
            <div className="cgrid">
              <div className="cfield"><small>From</small><span>{c.from.code} · {c.from.name}</span></div>
              <div className="cfield"><small>To</small><span>{c.to.code} · {c.to.name}</span></div>
              <div className="cfield"><small>Date</small><span>{c.date_irctc}</span></div>
              <div className="cfield"><small>Departs</small><span>{c.departs}</span></div>
              <div className="cfield"><small>Arrives</small><span>{c.arrives}{c.arrives_day_offset ? ` (+${c.arrives_day_offset})` : ""}</span></div>
              <div className="cfield"><small>Class · Quota</small><span>{c.travel_class} · {c.quota}</span></div>
            </div>
            <div className="table-scroll">
              <table className="ptable">
                <thead><tr><th>Passenger</th><th>Age</th><th>Gender</th><th>Berth</th></tr></thead>
                <tbody>{c.passengers.map((p) => <tr key={p.name}><td>{p.name}</td><td>{p.age}</td><td>{p.gender}</td><td>{p.berth}</td></tr>)}</tbody>
              </table>
            </div>
            <p>About {inr(c.fare_estimate_inr)} for everyone. {c.notes.join(" ")}</p>
            <div className="row-wrap">
              <button type="button" className="btn btn-cream" onClick={copy}>{copied ? "Copied" : "Copy all details"}</button>
              <a className="btn btn-primary" href={c.booking_url} target="_blank" rel="noopener noreferrer" onClick={() => track("booking_chosen")}>Open IRCTC</a>
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
      <div className="bk-sec-head"><h2 className="h2" id="pnr-h">Track a PNR</h2><span className="hint">Sample PNRs only in the prototype.</span></div>
      <form className="track" onSubmit={(e) => { e.preventDefault(); void check(pnr); }}>
        <label htmlFor="pnr" className="sr">PNR number</label>
        <input id="pnr" className="input" inputMode="numeric" maxLength={10} placeholder="10-digit PNR" value={pnr} onChange={(e) => setPnr(e.target.value)} />
        <button type="submit" className="btn btn-primary" disabled={res === "busy"}>Check</button>
      </form>
      <div className="q-chips">{SAMPLE_PNRS.map((p) => <button key={p} type="button" className="chip" onClick={() => void check(p)}>{p}</button>)}</div>
      {res === "busy" ? (
        <p className="hint" role="status">Checking…</p>
      ) : res?.problem ? (
        <Problem {...res.problem} onRetry={() => void check(pnr)} />
      ) : s && (
        <div className="panel panel-pad pnr">
          <div className="bk-sec-head">
            <b>{s.train} · {s.class} · {dayLabel(s.date)}</b>
            <span className={/CNF/.test(s.current_status) ? "badge badge-ok" : "badge badge-warn"}>{s.current_status}</span>
          </div>
          <p className="hint" style={{ margin: 0 }}>{s.from.name} to {s.to.name}{s.chart_prepared ? " · chart prepared" : ""}</p>
          <ol className="timeline">
            {[...s.timeline].sort((a, b) => Date.parse(b.at) - Date.parse(a.at)).map((t) => (
              <li key={t.at + t.status}><time dateTime={t.at}>{dayLabel(t.at)} {t.at.slice(11, 16)}</time><i /><span><b>{t.status}</b> {t.note}</span></li>
            ))}
          </ol>
        </div>
      )}
    </section>
  );
}

function Book({ it }: { it: Itinerary }) {
  const stored = useChoice();
  const way = (it.transport ?? [])[stored ?? pickIndex(it)];
  const cost = way ? tripCost(it, way) : it.budget.total_inr;
  const vs = againstBudget(it, cost);
  return (
    <>
      <div className="bk-top">
        <Trail at={5} />
        <h1 className="page-title">Book {it.request.destinations.join(" and ")}</h1>
        <p className="page-sub">We line everything up; you book and pay each seller directly. Nothing here charges you.</p>
      </div>
      <div className="bk-strip">
        <div><small>Whole trip, estimated</small><b>{inr(cost)}</b></div>
        <div><small>Budget</small><b>{it.request.constraints?.budget_inr ? inr(it.request.constraints.budget_inr) : "Not set"}</b></div>
        <div><small>{vs && !vs.ok ? "Over budget by" : "Left over"}</small><b>{vs ? inr(vs.diff) : "—"}</b></div>
      </div>
      <Travel it={it} />
      <TrainCard it={it} />
      <section className="bk-sec" aria-labelledby="stay-h">
        <div className="bk-sec-head"><h2 className="h2" id="stay-h">Where you stay</h2></div>
        {(it.stays ?? []).map((s) => (
          <article key={s.name} className="item">
            <span className="item-ic"><svg className="ic" viewBox="0 0 24 24" aria-hidden="true"><path d="M3 18V7" /><path d="M3 14h18v4" /><path d="M3 11h7a2 2 0 0 1 2 2v1" /><path d="M12 14v-2a2 2 0 0 1 2-2h5a2 2 0 0 1 2 2v2" /></svg></span>
            <div>
              <b>{s.name}</b>
              <span className="item-sub">{s.city} · {dayLabel(s.check_in)} to {dayLabel(s.check_out)} · {inr(s.price_per_night_inr)} a night</span>
              <Offers offers={s.offers} />
            </div>
          </article>
        ))}
        {!(it.stays ?? []).length && <p className="hint">No stay in this plan.</p>}
      </section>
      <section className="bk-sec" aria-labelledby="cab-h">
        <div className="bk-sec-head"><h2 className="h2" id="cab-h">Cabs</h2></div>
        <p className="hint" style={{ margin: 0 }}>Local cabs are booked on the day. Seller links for cabs come with the seller comparison.</p>
      </section>
      <PnrTrack />
      <p><Link href="/plan/itinerary/">Back to the day-by-day plan</Link></p>
    </>
  );
}

export default function BookPage() {
  const res = usePlanResult();
  return <AppShell>{res === undefined ? null : res ? <div><Book it={res.itinerary} /></div> : <NoPlan />}</AppShell>;
}
