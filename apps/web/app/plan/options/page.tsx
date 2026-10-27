"use client";

import Link from "next/link";
import { AppShell } from "@/components/AppShell";
import { NoPlan } from "@/components/NoPlan";
import { Trail } from "@/components/Trail";
import type { Itinerary } from "@/lib/contracts";
import { MODE_ICON, MODE_NAME, clock, dayLabel, duration, inr } from "@/lib/format";
import { saveChoice, useChoice, usePlanResult } from "@/lib/plan";
import { againstBudget, nights, pickIndex, travellerCount, tripCost } from "@/lib/planView";
import "../plan.css";

const star = <path d="M12 3l2.6 5.6 6 .7-4.5 4.1 1.2 6L12 16.4 6.7 19.4l1.2-6L3.4 9.3l6-.7Z" />;

function Options({ it }: { it: Itinerary }) {
  const opts = it.transport ?? [];
  const best = pickIndex(it);
  const stored = useChoice();
  const sel = stored != null && stored < opts.length ? stored : best;
  const choose = saveChoice;

  const dest = it.request.destinations.join(" and ");
  const people = travellerCount(it);
  const o = opts[sel];
  const cost = o ? tripCost(it, o) : it.budget.total_inr;
  const vs = againstBudget(it, cost);
  const b = it.budget;
  const bestOpt = opts[best];

  return (
    <>
      <div className="po-head">
        <Trail at={3} />
        <div className="col-10">
          <h1 className="page-title">{opts.length === 1 ? `One way to ${dest}` : `${opts.length} ways to ${dest}`}</h1>
          <p className="page-sub">
            Compared for {people > 1 ? `all ${people} of you` : "you"}. Costs are for the whole trip: travel, {nights(it)} nights&apos; stay, food and tickets.
          </p>
        </div>
      </div>

      {bestOpt && opts.length > 1 && (
        <div className="pick-note">
          <svg className="ic" viewBox="0 0 24 24" aria-hidden="true">{star}</svg>
          <div>
            <b>Our pick: {MODE_NAME[bestOpt.mode].toLowerCase()}</b>
            <span>{pickReason(it, best)}</span>
          </div>
        </div>
      )}

      <div className="opts" role="radiogroup" aria-label="Way to travel">
        {opts.map((x, i) => {
          const c = tripCost(it, x);
          const v = againstBudget(it, c);
          return (
            <button key={`${x.mode}-${i}`} type="button" role="radio" aria-checked={i === sel} className={i === sel ? "opt on" : "opt"} onClick={() => choose(i)}>
              <span className="opt-top">
                <span className="opt-ic"><svg className="ic" viewBox="0 0 24 24" aria-hidden="true"><path d={MODE_ICON[x.mode]} /></svg></span>
                <b>{MODE_NAME[x.mode]}{x.legs[0] ? `: ${x.legs[0].from} to ${x.legs.at(-1)!.to}` : ""}</b>
              </span>
              <span className="opt-figs">
                <span><small>Travel time</small><span>{duration(x.total_minutes)}</span></span>
                <span><small>Whole trip (est.)</small><span>{inr(c)}</span></span>
              </span>
              <span className="badges">
                {v && <span className={v.ok ? "badge badge-ok" : "badge badge-warn"}>{v.ok ? `${inr(v.diff)} to spare` : `Over by ${inr(v.diff)}`}</span>}
                <span className="badge">Comfort {x.comfort} of 5</span>
                {i === best && opts.length > 1 && <span className="badge badge-sea">Our pick</span>}
              </span>
              <span className="opt-line">{x.legs.length === 1 ? "Direct, no changes." : `${x.legs.length} legs, ${x.legs.length - 1} change${x.legs.length > 2 ? "s" : ""}.`}</span>
            </button>
          );
        })}
      </div>

      {o && (
        <div className="split">
          <section className="main panel panel-pad" aria-labelledby="d-h">
            <div className="detail-head">
              <h2 className="h2" id="d-h">{MODE_NAME[o.mode]}, step by step</h2>
              <span className="hint">Going, {dayLabel(o.legs[0]?.depart ?? it.request.start_date)}</span>
            </div>
            <div className="legs">
              {o.legs.map((l, i) => (
                <div className="leg-row" key={i}>
                  <span className="leg-when">{clock(l.depart)} to {clock(l.arrive)}</span>
                  <span className="leg-ic"><svg className="ic" viewBox="0 0 24 24" aria-hidden="true"><path d={MODE_ICON[l.mode]} /></svg></span>
                  <div>
                    <b>{l.from} to {l.to}</b>
                    <small>{MODE_NAME[l.mode]} · {duration(l.minutes)} · {inr(l.cost_inr)}{people > 1 ? ` for ${people}` : ""}</small>
                  </div>
                </div>
              ))}
            </div>
          </section>

          <aside className="side panel panel-pad" aria-labelledby="c-h">
            <h2 className="h3" id="c-h" style={{ marginBottom: 14 }}>Where the money goes</h2>
            <dl className="kv cost">
              <dt>Getting there, {MODE_NAME[o.mode].toLowerCase()}</dt><dd>{inr(o.total_cost_inr)}</dd>
              <dt>Stay</dt><dd>{inr(b.stay_inr)}</dd>
              {!!b.food_inr && <><dt>Food</dt><dd>{inr(b.food_inr)}</dd></>}
              {!!b.activities_inr && <><dt>Tickets and activities</dt><dd>{inr(b.activities_inr)}</dd></>}
              <dt className="tot">Whole trip, estimated</dt><dd className="tot">{inr(cost)}</dd>
            </dl>
            {vs && <p className={vs.ok ? "badge badge-ok" : "badge badge-warn"} style={{ marginTop: 14 }}>{vs.ok ? `${inr(vs.diff)} under your budget` : `${inr(vs.diff)} over your budget`}</p>}
          </aside>
        </div>
      )}

      <p className="hint" style={{ margin: "16px 0 0" }}>Fares are estimates from sample data until live prices are wired in. You pay the seller directly when you book.</p>

      <div className="go">
        <div><b>{o ? `Go by ${MODE_NAME[o.mode].toLowerCase()}` : "See the plan"}</b><span>Next, the day-by-day plan. You can still switch later.</span></div>
        <Link className="btn btn-primary btn-lg" href="/plan/itinerary/">See the day-by-day plan</Link>
      </div>
    </>
  );
}

function pickReason(it: Itinerary, best: number): string {
  const opts = it.transport ?? [];
  const o = opts[best];
  const c = tripCost(it, o);
  const v = againstBudget(it, c);
  const parts = [v ? (v.ok ? `It fits the budget with ${inr(v.diff)} to spare` : `It is the closest to your budget`) : "It costs the least"];
  const faster = opts.filter((x) => x.total_minutes < o.total_minutes).sort((a, b) => a.total_minutes - b.total_minutes)[0];
  if (faster && tripCost(it, faster) > c) parts.push(`${MODE_NAME[faster.mode]} is ${duration(o.total_minutes - faster.total_minutes)} quicker but costs ${inr(tripCost(it, faster) - c)} more`);
  return parts.join(". ") + ".";
}

export default function PlanOptions() {
  const res = usePlanResult();
  const it = res === undefined ? undefined : (res?.itinerary ?? null);
  return <AppShell>{it === undefined ? null : it ? <div><Options it={it} /></div> : <NoPlan />}</AppShell>;
}
